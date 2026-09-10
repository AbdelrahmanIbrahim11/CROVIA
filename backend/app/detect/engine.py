"""
The orchestrator, and the part that only matters once the city has more than
one crowd at the same time.

With a single incident there is nothing to decide: spend what is needed. With
two, a fixed hourly budget has to be split, and splitting it evenly is the
wrong answer. Three half-funded answers are three samples too small to act on.
One funded answer plus two honestly marked "unresolved" is more useful.

So each tick does this:

  1. For every district, gather the evidence that costs nothing. Congestion
     arrives pushed; the panel count from the previous tick is already held.
  2. Rank the districts that look like they need attention.
  3. Ask the budget to split what is available, urgency first.
  4. Spend only where funding was granted, and record the rest as unresolved
     rather than pretending they were checked.

The state per district is independent, so two crowds never overwrite each
other's evidence.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable

from app.camara.client import Area, ApiError, CamaraClient
from app.core.budget import Budget, Ledger, Request
from app.core.city import City
from app.core.registry import DeviceRegistry
from app.detect.danger import Evidence, Verdict, assess

IDLE, WATCHING, CONFIRMING, ALERT, STANDDOWN = "IDLE", "WATCHING", "CONFIRMING", "ALERT", "STANDDOWN"


@dataclass
class ZoneState:
    zone_id: str
    district_id: str
    counts: deque = field(default_factory=lambda: deque(maxlen=30))  # (t, people)
    filling_since: float | None = None
    last_verdict: Verdict | None = None
    last_checked: float = 0.0
    unresolved_since: float | None = None
    alerted: bool = False
    next_check_at: float = 0.0
    consecutive_high: int = 0

    # How far back the fill rate looks. Long enough to be steady, short enough
    # to still be about now.
    RATE_MIN_SPAN_S = 120.0
    RATE_MAX_SPAN_S = 420.0

    def rate_per_min(self) -> float:
        """
        How fast the headcount is changing, in real people per minute.

        Measured over a short recent window, not the whole history. Averaging
        across every sample ever taken smooths a surge into nothing: with five
        minutes between samples and thirty samples kept, the window stretched to
        two and a half hours and a crush that built in ten minutes never showed
        up as a rate at all.
        """
        if len(self.counts) < 2:
            return 0.0
        t_now = self.counts[-1][0]
        window = [(t, p) for t, p in self.counts if t_now - t <= self.RATE_MAX_SPAN_S]
        if len(window) < 2 or (t_now - window[0][0]) < self.RATE_MIN_SPAN_S:
            return 0.0
        # Least-squares slope across the window, rather than the difference
        # between the first and last points.
        #
        # Each counted device stands for hundreds of people, so a single sample
        # lands on a coarse grid and two samples can differ by that step size
        # purely by chance. Taking the difference of two noisy endpoints turned
        # that noise straight into a fake rate; a slope through every point in
        # the window averages it out instead.
        n = len(window)
        mt = sum(t for t, _ in window) / n
        mp = sum(p for _, p in window) / n
        num = sum((t - mt) * (p - mp) for t, p in window)
        den = sum((t - mt) ** 2 for t, _ in window)
        if den <= 0:
            return 0.0
        return (num / den) * 60.0

    def span_s(self) -> float:
        if len(self.counts) < 2:
            return 0.0
        return self.counts[-1][0] - self.counts[0][0]


@dataclass
class ScheduledEvent:
    """
    A crowd we know about in advance: a match, a concert, a prayer time.

    This is the earliest and cheapest trigger there is, because it costs no API
    calls at all. It matters more than it first appears: congestion is pushed
    every few minutes per device, so by the time enough devices have reported
    for a district to look unusual, a stadium crowd has already formed. In
    testing, the first count landed at t=905 s with 13,000 people already in the
    zone — the fill had happened entirely unobserved. Watching from before the
    doors open is what turns this from a late report into a warning.
    """

    zone_id: str
    starts_at: float
    expected_attendance: int
    duration_s: float = 12 * 60.0
    lead_s: float = 30 * 60.0
    label: str = ""

    def expected_inflow_per_min(self) -> float:
        """People per minute this event will send at the zone."""
        return self.expected_attendance / max(self.duration_s / 60.0, 1.0)

    def active(self, now: float) -> bool:
        return (self.starts_at - self.lead_s) <= now <= (self.starts_at + 90 * 60.0)


@dataclass
class DistrictState:
    district_id: str
    state: str = IDLE
    high_devices: dict = field(default_factory=dict)   # hashed -> last seen at
    armed_at: float | None = None


class Engine:
    # How often a zone is counted, and with how many devices, depending on what
    # it is doing. Counting every zone every 30 seconds at full sample spends an
    # entire hourly budget in a few minutes, after which nothing can be watched
    # at all — which is how two simultaneous crushes ended up starving each
    # other. Quiet places are cheap to watch slowly; only a place that is
    # actually filling deserves the full sample and a fast cadence.
    # Sample size is a precision decision, not only a cost one. Each counted
    # device stands for population/panel people, so a sample of 18 moves the
    # estimate in jumps of well over a thousand — far larger than the change
    # being looked for. Idle places can afford that coarseness; a place that is
    # filling cannot.
    # Chosen by measurement, not by taste. Three settings were swept across
    # thirty runs (see sim/sweep.py):
    #
    #   cheap     100% caught, 1 false alarm,  1,872 calls
    #   balanced  100% caught, 0 false alarms, 1,958 calls   <- this one
    #   precise   100% caught, 1 false alarm,  2,385 calls
    #
    # Spending more is not simply better: the most aggressive setting samples
    # marginal situations often enough to talk itself into one false alarm,
    # while costing 22% more. Balanced is clean on both counts for 5% more than
    # the cheapest option.
    CADENCE = {
        IDLE:       (300.0, 30),   # every 5 min, coarse
        WATCHING:   (90.0, 80),    # every 90 s once something is happening
        CONFIRMING: (60.0, 110),   # every minute, oversampled
        ALERT:      (60.0, 110),
        STANDDOWN:  (300.0, 30),
    }

    def __init__(self, city: City, client: CamaraClient, registry: DeviceRegistry,
                 budget: Budget | None = None, panel_sample: int = 45,
                 seed: int = 5) -> None:
        self.city = city
        self.client = client
        self.registry = registry
        self.budget = budget or Budget()
        self.panel_sample = panel_sample
        self.ledger: Ledger = client.ledger
        self.districts = {d: DistrictState(d) for d in city.districts}
        self.zones = {z.id: ZoneState(z.id, z.district_id) for z in city.zones.values()}
        self.trace: list[dict] = []
        self.alerts: list[dict] = []
        self.now = 0.0
        self._rng = random.Random(seed)
        self.schedule: list[ScheduledEvent] = []
        self.predictions: list[dict] = []
        self._announced: set[str] = set()
        # Optional hooks so an alarm can be written somewhere durable. They stay
        # optional because the engine has to run inside the simulation with no
        # database at all, and a detection engine that needs a database to
        # decide anything is a detection engine that stops during an outage.
        self.on_alert_raised: Callable[[dict], None] | None = None
        self.on_alert_cleared: Callable[[str, float], None] | None = None

    # ------------------------------------------------------------------

    def add_scheduled(self, ev: ScheduledEvent) -> None:
        self.schedule.append(ev)

    def _scheduled_zones(self) -> set[str]:
        """
        Zones with a known event, and the free prediction that comes with them.

        For a scheduled crowd the danger can be worked out before anyone moves,
        from two numbers we already have: how many people are expected and over
        what period, against how many the narrowest link can pass. Both come
        from the fixture list and the city plan, so this costs nothing and is
        available before the first person leaves their seat.

        It is a PREDICTION, not a measurement, and is labelled that way. What it
        buys is the decision to watch closely from the start, and a warning to
        an operator while there is still time to open another gate. Measurement
        then confirms it or takes it back.
        """
        live = set()
        for ev in self.schedule:
            if not ev.active(self.now):
                continue
            live.add(ev.zone_id)
            key = f"{ev.zone_id}:{ev.starts_at}"
            if key in self._announced:
                continue
            self._announced.add(key)
            mins = (ev.starts_at - self.now) / 60.0
            inflow = ev.expected_inflow_per_min()
            capacity = self.city.zone_capacity_per_min(ev.zone_id)
            hazard = self.city.bottleneck_of(ev.zone_id)
            width = hazard.width_m if hazard else 0.0
            if inflow > capacity:
                self.predictions.append({
                    "t": self.now, "zone_id": ev.zone_id, "predicted": True,
                    "expected_inflow_per_min": round(inflow),
                    "capacity_per_min": round(capacity),
                    "segment": hazard.id if hazard else None,
                    "segment_label": hazard.label if hazard else "unlocated",
                })
                self.log("predict",
                         f"{ev.label or ev.zone_id[5:]} in {mins:.0f} min: about "
                         f"{ev.expected_attendance:,} people over "
                         f"{ev.duration_s/60:.0f} min is ~{inflow:,.0f}/min, against a "
                         f"{width:.0f} m link that passes ~{capacity:,.0f}/min. "
                         "More will arrive than can leave - predicted before anyone moves.",
                         zone=ev.zone_id, predicted=True)
            else:
                self.log("prearm",
                         f"{ev.label or ev.zone_id[5:]} in {mins:.0f} min "
                         f"(~{ev.expected_attendance:,} people, ~{inflow:,.0f}/min against "
                         f"{capacity:,.0f}/min capacity) - within capacity, watching anyway",
                         zone=ev.zone_id)
        return live

    def log(self, kind: str, msg: str, **extra) -> None:
        self.trace.append({"t": self.now, "kind": kind, "msg": msg, **extra})

    # ---- free evidence -------------------------------------------------

    def on_congestion(self, sub_id: str, level: str, confidence: int) -> None:
        """
        A congestion notification. It carries no location and no device id, so
        the district can only come from our own registry, which the district
        geofences keep up to date.
        """
        if level not in ("High", "Medium") or confidence < 50:
            return
        hashed = self.registry.sub_device.get(sub_id)
        if not hashed:
            return
        district = self.registry.district_of(hashed)
        if not district:
            return
        self.districts[district].high_devices[hashed] = self.now

    def on_congestion_device(self, hashed: str, level: str, confidence: int) -> None:
        """
        Congestion for a device we already know, identified by its own webhook
        address rather than by anything in the message.

        The notification itself names neither a device nor a subscription, so
        this is the only way the signal can be placed on the map at all.
        """
        if level not in ("High", "Medium") or confidence < 50:
            return
        district = self.registry.district_of(hashed)
        if not district:
            return
        self.districts[district].high_devices[hashed] = self.now

    def on_geofence(self, sub_id: str, event_type: str) -> None:
        hashed = self.registry.sub_device.get(sub_id)
        area = self.registry.sub_area.get(sub_id)
        kind = self.registry.sub_kind.get(sub_id)
        if not hashed or not area:
            return
        if kind == "district":
            if event_type == "area-entered":
                self.registry.place(hashed, area, self.now)
            else:
                self.registry.remove_from(hashed, area)

    def on_subscription_end(self, sub_id: str) -> None:
        """
        A subscription has expired or been terminated at the operator.

        This has to be visible, because the failure it causes is silent: events
        for that device simply stop arriving, and a city with no events looks
        exactly like a calm one. The binding is dropped so the device is no
        longer counted as located, which at least makes the loss measurable.
        """
        hashed = self.registry.sub_device.pop(sub_id, None)
        kind = self.registry.sub_kind.pop(sub_id, None)
        area = self.registry.sub_area.pop(sub_id, None)
        if hashed and kind == "district" and area:
            self.registry.remove_from(hashed, area)
        self.log("subscription_end",
                 f"{kind or 'unknown'} subscription ended for area {area or '-'} - "
                 "that device is no longer reporting", sub_id=sub_id)

    def _prune(self, window_s: float = 900.0) -> None:
        cut = self.now - window_s
        for st in self.districts.values():
            for h in [h for h, t in st.high_devices.items() if t < cut]:
                st.high_devices.pop(h, None)

    def _congestion_signal(self) -> dict[str, float]:
        """Share of each district's fleet reporting congestion."""
        out = {}
        for did, st in self.districts.items():
            fleet = max(len(self.registry.fleet(did)), 1)
            out[did] = len(st.high_devices) / fleet
        return out

    # ---- paid evidence -------------------------------------------------

    def count_zone(self, zone_id: str, max_calls: int) -> tuple[float, int, int]:
        """
        Count people inside a zone using Location Verification.

        This is the main sensor. It needs no subscription, returns no
        coordinates, and works even though sandbox devices never move — which
        is why it replaced counting geofence crossings.

        Returns (people, inside, checked).
        """
        z = self.city.zones[zone_id]
        area = Area(z.center.lat, z.center.lon, z.radius_m)
        panel = self.registry.panel_members()
        if not panel:
            return 0.0, 0, 0

        take = min(self.panel_sample, len(panel), max_calls)
        # Draw a FRESH random subset every time. Taking the first N of a stable
        # list asks the same people on every cycle, so if none of them happen to
        # be near the crowd the count stays near zero for ever. That is worst
        # exactly when budget is tight and the subset is smallest.
        chosen = self._rng.sample(panel, take) if take < len(panel) else list(panel)
        inside = checked = 0
        for hashed in chosen:
            phone = self.registry.vault.phone_for(hashed)
            if not phone:
                continue
            try:
                r = self.client.verify_location(phone, area, z.district_id)
            except ApiError:
                continue
            self.budget.spend(1, self.now)
            checked += 1
            res = r["verification_result"]
            if res == "TRUE" or (res == "PARTIAL" and r.get("match_rate", 0) >= 55):
                inside += 1

        people = self.registry.people_from_panel(inside, checked, self.city.population)
        return people, inside, checked

    # ---- the tick ------------------------------------------------------

    def tick(self, now: float | None = None) -> list[Verdict]:
        self.now = time.time() if now is None else now
        self._prune()

        scheduled = self._scheduled_zones()
        shares = self._congestion_signal()
        vals = sorted(shares.values())
        # Compare against the QUIETEST district, not the middle or the quartile.
        #
        # The median works while exactly one district is busy, and the lower
        # quartile works while at most one is. With three of four busy the
        # quartile lands on a busy district itself, so nothing looks unusual and
        # three simultaneous crushes went undetected. The minimum stays low as
        # long as any part of the city is calm, and the case where nothing is
        # calm is already handled separately as a network fault.
        baseline = vals[0] if vals else 0.0
        # A network fault raises congestion everywhere, including places where
        # nobody has gathered. Suppression therefore requires EVERY district to
        # be elevated, not most of them.
        #
        # Requiring only "most" was wrong: three genuine crowds in three of four
        # districts looked identical to a fault and were suppressed, so the
        # three-crowd scenario detected nothing at all. Demanding all four means
        # a real fault costs a little counting before it is dismissed, which is
        # much cheaper than missing three simultaneous crushes.
        city_wide = all(v > 0.35 for v in shares.values()) and len(shares) > 1

        # 1. Which zones deserve paid attention?
        wanted: list[Request] = []
        for zid, zs in self.zones.items():
            did = zs.district_id
            share = shares.get(did, 0.0)
            interesting = (
                # A known event beats every measured signal, and costs nothing.
                zid in scheduled
            ) or (
                not city_wide
                and (
                    # unusual against the calm parts of the city
                    (share >= 0.10 and share >= 2.0 * max(baseline, 0.02))
                    # or simply strong on its own, which matters when several
                    # districts are busy and comparison alone is ambiguous
                    or share >= 0.25
                )
            ) or self.districts[did].state in (WATCHING, CONFIRMING, ALERT) or zs.rate_per_min() > 0
            if not interesting:
                continue
            # Respect this zone's own cadence.
            state = ALERT if zs.alerted else self.districts[did].state
            interval, sample = self.CADENCE.get(state, (300.0, 22))
            # Congestion is free and arrives early. Treating it as a reason to
            # look more closely — rather than waiting until a rate has already
            # been measured — is what buys the warning time.
            if state == IDLE and (zid in scheduled or zs.rate_per_min() > 0 or share >= 0.20):
                interval, sample = self.CADENCE[WATCHING]
            if self.now < zs.next_check_at:
                continue

            last = zs.last_verdict
            wanted.append(Request(
                district_id=did, zone_id=zid,
                calls_wanted=sample,
                severity=last.severity if last else 0.4,
                people=last.people_low if last else 0.0,
                seconds_to_critical=last.seconds_to_critical if last else None,
            ))

        if city_wide:
            self.log("suppress", "every district is elevated together - that is a network "
                                 "event, not a crowd. Not spending.")
            return []
        if not wanted:
            return []

        # 2. Split the money, urgency first.
        grants = self.budget.allocate(wanted, self.now)
        if len(wanted) > 1:
            self.log("allocate",
                     f"{len(wanted)} zones want attention; budget split "
                     + ", ".join(f"{r.zone_id[5:]}={grants.get(r.zone_id, 0)}" for r in wanted),
                     grants={r.zone_id: grants.get(r.zone_id, 0) for r in wanted})

        # 3. Spend where funded.
        verdicts: list[Verdict] = []
        for req in wanted:
            zs = self.zones[req.zone_id]
            allowed = grants.get(req.zone_id, 0)
            if allowed <= 0:
                zs.unresolved_since = zs.unresolved_since or self.now
                self.log("unresolved",
                         f"{req.zone_id[5:]}: no budget this cycle - marked unresolved, "
                         "not silently treated as safe", zone=req.zone_id)
                continue

            people, inside, checked = self.count_zone(req.zone_id, allowed)
            if checked == 0:
                continue
            state_now = ALERT if zs.alerted else self.districts[req.district_id].state
            zs.next_check_at = self.now + self.CADENCE.get(state_now, (300.0, 18))[0]
            zs.unresolved_since = None
            zs.counts.append((self.now, people))
            zs.last_checked = self.now

            rate = zs.rate_per_min()
            capacity = self.city.zone_capacity_per_min(req.zone_id)
            # Hysteresis, and a run of confirmations before the clock starts.
            #
            # Each counted device stands for hundreds of people, so a single
            # cycle can read high or low purely by chance. Starting the clock on
            # one high reading let a safe staggered release raise an alarm, and
            # clearing it on one low reading kept resetting a real crush back to
            # zero. So: start high, clear only when clearly low, and require two
            # consecutive high readings before the fill is believed.
            #
            # Two confirmations replace most of the old sustained timer rather
            # than adding to it. Demanding three confirmations AND four minutes
            # on the clock asked for the same evidence twice and detected
            # nothing at all.
            if rate >= 0.60 * capacity:
                zs.consecutive_high += 1
                if zs.consecutive_high >= 2:
                    zs.filling_since = zs.filling_since or self.now
            elif rate < 0.35 * capacity:
                zs.consecutive_high = 0
                zs.filling_since = None
            sustained = 0.0 if zs.filling_since is None else self.now - zs.filling_since

            v = assess(self.city, Evidence(
                zone_id=req.zone_id, people=people, people_rate_per_min=rate,
                inside_sampled=inside, sustained_s=sustained,
            ))
            # A zone whose danger was predicted from the fixture list does not
            # have to re-prove that it is a crowd. Prediction plus a measured
            # rise is enough, which is what recovers the warning time that
            # waiting for full statistical confirmation gives away.
            if (not v.dangerous and not zs.alerted and rate > 0
                    and any(pr["zone_id"] == req.zone_id for pr in self.predictions)):
                cap = self.city.zone_capacity_per_min(req.zone_id)
                if rate >= 0.45 * cap and zs.consecutive_high >= 1:
                    v.dangerous = True
                    v.fired_by = "predicted_and_rising"
                    v.reason = (f"predicted before the event; measurement confirms it "
                                f"filling at {rate:,.0f}/min against {cap:,.0f}/min capacity")

            zs.last_verdict = v
            verdicts.append(v)

            # Alert state belongs to the ZONE, not the district. A district can
            # hold several zones, and when one of them was calm the district was
            # being reset out of ALERT, which let the dangerous zone re-fire on
            # the next tick. One crowd produced thirteen alerts that way.
            ds = self.districts[req.district_id]
            if v.dangerous:
                if not zs.alerted:
                    zs.alerted = True
                    record = {"t": self.now, **v.to_dict()}
                    self.alerts.append(record)
                    self.log("alert", f"{v.hazard_label}: {v.reason}", **v.to_dict())
                    self._notify(self.on_alert_raised, record)
                ds.state = ALERT
            else:
                if zs.alerted and rate <= 0:
                    zs.alerted = False
                    self.log("standdown", f"{req.zone_id[5:]} is clearing", zone=req.zone_id)
                    self._notify(self.on_alert_cleared, req.zone_id, self.now)
                # The district stays in ALERT while ANY of its zones is alerted.
                any_alerted = any(self.zones[z.id].alerted
                                  for z in self.city.zones_of(req.district_id))
                ds.state = ALERT if any_alerted else (WATCHING if rate > 0 else IDLE)

        return verdicts

    def _notify(self, hook: Callable | None, *args) -> None:
        """
        Run a hook without ever letting it break detection.

        A database that is briefly unreachable must not stop the engine from
        judging the next zone. The failure is logged as a trace entry so it is
        visible rather than silent.
        """
        if hook is None:
            return
        try:
            hook(*args)
        except Exception as exc:
            self.log("hook_failed", f"could not record the alarm: {exc}")

    def snapshot(self) -> dict:
        return {
            "t": self.now,
            "districts": {d: s.state for d, s in self.districts.items()},
            "zones": {z: (s.last_verdict.to_dict() if s.last_verdict else None)
                      for z, s in self.zones.items()},
            "unresolved": [z for z, s in self.zones.items() if s.unresolved_since],
            "spend": self.ledger.summary(),
            "alerts": len(self.alerts),
        }
