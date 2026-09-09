"""
The verdict. Deterministic, auditable, and deliberately not clever.

No model decides whether people are in danger. After an incident someone will
ask "why did it fire?" or, far worse, "why did it not?", and the answer has to
be a rule anyone can check by hand.

WHAT THIS DOES NOT DO
---------------------
It does not claim a measured density at the pinch point. Positioning error is
150-400 m and the dangerous link is often under 130 m long, so fixes cannot be
resolved onto it. An earlier version tried, matched the crowd onto the wide
neighbouring segments, and reported 0.3 people/m2 while the truth on the ramp
was 5.2. Density at the pinch is INFERRED instead, from three things that are
genuinely knowable:

    how many people are inside      unbiased, from the citywide panel
    whether they are getting out    ratios, so free of sample bias
    where the pinch is and how wide from the city plan, no measurement at all

A large crowd that cannot clear a known narrow link is compressed against that
link. That inference needs no sub-100 m accuracy.

THE THREE WAYS IT FIRES
-----------------------
  A. FILLING      arrivals exceed what the narrowest link can pass. Earliest,
                  and the only one that can warn before the crowd is trapped.
  B. NOT CLEARING people inside are not coming out. Later, but certain.
  C. DENSITY      the corridor as a whole is past the Fruin threshold.

None fires while the place is draining. A dense crowd that is moving is a busy
street, not a disaster — and treating the two the same is how a system trains
its operators to ignore it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.city import City, Segment

# Fruin-derived bands, people per square metre.
BANDS = [
    (2.0, "free", "Free flow"),
    (4.0, "restricted", "Restricted but managing"),
    (5.0, "risk", "Risk onset - people lose control of their own movement"),
    (6.0, "critical", "Crowd moves as a fluid; falls cascade"),
    (99.0, "crush", "Crush - compressive asphyxia risk"),
]


def band_for(density: float) -> tuple[str, str]:
    for limit, key, label in BANDS:
        if density < limit:
            return key, label
    return "crush", "Crush"


@dataclass
class Evidence:
    """Everything measured about one zone at one moment."""

    zone_id: str
    people: float                    # unbiased, from the panel
    people_rate_per_min: float       # change in that number
    inside_sampled: int              # how many devices backed it
    outflow_ratio: float | None = None   # exits vs the cohort that entered
    dwell_ratio: float | None = None     # dwell against free crossing time
    sustained_s: float = 0.0             # how long it has been filling


@dataclass
class Verdict:
    zone_id: str
    dangerous: bool
    reason: str
    hazard_segment_id: str | None
    hazard_label: str
    hazard_width_m: float
    capacity_per_min: float
    people_low: float
    people_high: float
    corridor_density: float
    inferred_pinch_density: float
    band: str
    band_label: str
    seconds_to_critical: float | None
    severity: float                  # 0..1, used to prioritise spend
    fired_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id, "dangerous": self.dangerous,
            "reason": self.reason, "segment": self.hazard_segment_id,
            "segment_label": self.hazard_label, "width_m": self.hazard_width_m,
            "capacity_per_min": round(self.capacity_per_min),
            "people_low": round(self.people_low), "people_high": round(self.people_high),
            "corridor_density": round(self.corridor_density, 2),
            "pinch_density": round(self.inferred_pinch_density, 2),
            "band": self.band, "band_label": self.band_label,
            "seconds_to_critical": (None if self.seconds_to_critical is None
                                    else round(self.seconds_to_critical)),
            "severity": round(self.severity, 2), "fired_by": self.fired_by,
        }


# A crowd smaller than this cannot be dangerous no matter how slowly it moves.
MIN_PEOPLE = 1200
# Never publish a figure backed by fewer devices than this.
K_ANONYMITY = 5
# Net arrivals must reach this share of capacity before "filling" fires. A
# merely positive rate is not evidence: a corridor filling toward a comfortable
# steady state does that too, and at 20% this produced a false alarm on a safe
# staggered release.
FILLING_FRACTION = 0.60
# Below this share of the entering cohort coming out, the place is not clearing.
OUTFLOW_COLLAPSE = 0.30
# Dwell longer than this multiple of the free crossing time means stuck.
DWELL_STUCK = 1.8


def assess(city: City, ev: Evidence) -> Verdict:
    hazard: Segment | None = city.bottleneck_of(ev.zone_id)
    capacity = city.zone_capacity_per_min(ev.zone_id)
    corridor_area = city.corridor_area_m2(ev.zone_id)
    risk = hazard.risk if hazard else 1.0

    # The penetration estimate behind the headcount carries real error, so the
    # number is published as a band rather than a falsely exact figure.
    low, high = ev.people * 0.7, ev.people * 1.4
    corridor_density = ev.people / max(corridor_area, 1.0)

    # --- the three tests ---------------------------------------------------
    filling = (
        ev.sustained_s >= 240.0
        and ev.people_rate_per_min >= FILLING_FRACTION * capacity
        and risk >= 1.4
        and ev.people >= MIN_PEOPLE
    )
    not_clearing = (
        (ev.outflow_ratio is not None and ev.outflow_ratio < OUTFLOW_COLLAPSE)
        or (ev.dwell_ratio is not None and ev.dwell_ratio >= DWELL_STUCK)
    )
    threshold = city.density_critical / max(risk, 1.0)
    over_density = corridor_density >= threshold

    draining = ev.people_rate_per_min <= 0 and not not_clearing
    enough_people = ev.people >= MIN_PEOPLE
    enough_devices = ev.inside_sampled >= K_ANONYMITY

    # People who cannot pass queue against the narrow link, so they occupy it
    # at or near jam density.
    pinch_area = hazard.area_m2 if hazard else corridor_area
    if (filling or not_clearing) and hazard:
        inferred = min(ev.people, city.constants["density_jam_p_per_m2"] * pinch_area) / pinch_area
    else:
        inferred = corridor_density

    seconds_to_critical = None
    if ev.people_rate_per_min > 0 and hazard:
        headroom = hazard.max_safe_people(city.density_critical) - ev.people
        if headroom > 0:
            seconds_to_critical = headroom / ev.people_rate_per_min * 60.0

    dangerous, fired_by, reason = False, None, ""

    if not enough_devices:
        reason = (f"only {ev.inside_sampled} devices inside - below the minimum of "
                  f"{K_ANONYMITY}, reporting at district level only")
    elif filling and enough_people:
        dangerous, fired_by = True, "filling"
        reason = (f"arriving at about {ev.people_rate_per_min:,.0f} people/min against a "
                  f"{hazard.width_m:.0f} m link that can pass ~{capacity:,.0f}/min - "
                  f"more are coming in than can get out")
    elif not_clearing and enough_people:
        dangerous, fired_by = True, "not_clearing"
        how = (f"only {ev.outflow_ratio:.0%} of the arriving group has come out"
               if ev.outflow_ratio is not None and ev.outflow_ratio < OUTFLOW_COLLAPSE
               else f"people inside are taking {ev.dwell_ratio:.1f}x the normal walking time")
        reason = (f"{low:,.0f}-{high:,.0f} people and they are not clearing ({how}). "
                  f"The narrowest link is {hazard.width_m:.0f} m")
    elif over_density and enough_people and not draining:
        dangerous, fired_by = True, "density"
        reason = (f"corridor at {corridor_density:.1f} people/m2, past the "
                  f"{threshold:.1f} limit for this geometry")
    elif draining:
        reason = f"draining - about {ev.people:,.0f} people passing through normally"
    elif not enough_people:
        reason = f"only about {ev.people:,.0f} people present - too few to be dangerous"
    else:
        reason = (f"about {ev.people:,.0f} people, still clearing "
                  f"({ev.people_rate_per_min:+,.0f}/min)")

    band, band_label = band_for(inferred if dangerous else corridor_density)

    # Severity drives which crowd gets the budget when two happen at once.
    severity = 0.0
    if enough_devices:
        severity = min(1.0, max(
            ev.people_rate_per_min / max(capacity, 1.0),
            inferred / max(city.density_critical, 1.0) * 0.8,
        ))
        if dangerous:
            severity = max(severity, 0.75)

    return Verdict(
        zone_id=ev.zone_id, dangerous=dangerous, reason=reason,
        hazard_segment_id=hazard.id if hazard else None,
        hazard_label=hazard.label if hazard else "unlocated",
        hazard_width_m=hazard.width_m if hazard else 0.0,
        capacity_per_min=capacity, people_low=low, people_high=high,
        corridor_density=corridor_density, inferred_pinch_density=inferred,
        band=band, band_label=band_label,
        seconds_to_critical=seconds_to_critical, severity=severity, fired_by=fired_by,
    )
