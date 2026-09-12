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
from app.core.city import City, LatLon
from app.core.registry import DeviceRegistry
from app.detect.danger import (K_ANONYMITY as K_ANON_MIN, Evidence, Verdict,
                               assess)

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
    # What this zone asked for on the cycle it was funded, so the wait can
    # honour the zone's own urgency rather than its district's stale state.
    next_interval: float | None = None
    consecutive_high: int = 0
    # Readings in a row showing the crowd is going down. Firing already needs
    # two confirmations; standing down needs them too, or the alarm flaps.
    consecutive_low: int = 0
    # Who was found inside last time, and when each device was first seen
    # there. Without these the engine can only measure the NET change in a
    # headcount, which cannot tell a crowd flowing through a place from a crowd
    # stuck in it - and those need opposite responses.
    # This zone's ordinary headcount, learned while nothing is wrong. A
    # residential district's normal population must not read as a crowd.
    baseline: float | None = None
    cohort: set = field(default_factory=set)
    cohort_at: float = 0.0
    inside_first_seen: dict = field(default_factory=dict)

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
        # Bounded on purpose.
        #
        # These are the live view, not the record: alarms are written to the
        # incidents table and warnings to alert_deliveries, both of which
        # survive a restart. Keeping every trace line for ever is how a service
        # that is never restarted slowly fills its memory - and on a 512 MB
        # instance that is a crash, days later, with no obvious cause.
        #
        # The API only ever returns the last few of each, so nothing is lost
        # that anybody reads.
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
                if len(self.predictions) > self.MAX_PREDICTIONS:
                    del self.predictions[:-self.MAX_PREDICTIONS]
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

    # How much of each to keep in memory. Generous next to what is read, small
    # next to what would accumulate over a week.
    MAX_TRACE = 500
    MAX_ALERTS = 200
    # How many previously-inside devices to re-ask, to see who left.
    #
    # Kept small on purpose. These calls come out of the same budget as the
    # headcount, and at eighteen they crowded it out: the count grew noisy, the
    # measured fill rate swung above and below its threshold, the run of
    # confirmations never reached two, and a genuine crush produced no alarm at
    # all. Knowing who left is worth far less than counting well.
    COHORT_SIZE = 10
    MAX_PREDICTIONS = 50

    def log(self, kind: str, msg: str, **extra) -> None:
        self.trace.append({"t": self.now, "kind": kind, "msg": msg, **extra})
        if len(self.trace) > self.MAX_TRACE:
            del self.trace[:-self.MAX_TRACE]

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

    # Below this many devices a district's share is noise, not a measurement.
    #
    # The share is a fraction of the district's fleet, so a small fleet makes
    # every single device enormous: with four devices one of them reporting
    # congestion is a share of 0.25, which clears the strongest trigger on its
    # own. Someone walking past a busy cafe would fund a paid count.
    #
    # It also protects the comparison. The baseline is the QUIETEST district,
    # and a district holding nobody reported a share of exactly zero - so an
    # empty district silently became the yardstick the whole city was measured
    # against.
    MIN_FLEET = 25

    def _congestion_signal(self) -> dict[str, float]:
        """
        Share of each district's fleet reporting congestion.

        Only districts with enough devices to be trusted appear here. A thin or
        empty district is absent rather than zero, because zero is a claim -
        "nothing is happening there" - and we have not measured anything.
        """
        out = {}
        for did, st in self.districts.items():
            fleet = set(self.registry.fleet(did))
            if len(fleet) < self.MIN_FLEET:
                continue
            # Count only devices STILL in this district.
            #
            # A device that reported congestion and then walked into another
            # district stayed in this list, while the fleet it was divided by
            # shrank - so the share climbed as a district emptied, and was
            # measured at 1.28 in testing. A fraction above 1.0 is not a busy
            # district, it is arithmetic about people who have left.
            busy = sum(1 for h in st.high_devices if h in fleet)
            out[did] = busy / len(fleet)
        return out

    def coverage(self) -> dict[str, dict]:
        """
        How many devices are watching each district, and whether that is enough.

        Reported so an operator is told "we cannot see the Marina" instead of
        being shown a calm-looking Marina. A district nobody is watching is the
        most dangerous thing to paint green.
        """
        out = {}
        for did in self.districts:
            n = len(self.registry.fleet(did))
            out[did] = {
                "devices": n,
                "trusted": n >= self.MIN_FLEET,
                "state": ("watched" if n >= self.MIN_FLEET
                          else "no coverage" if n == 0 else "thin coverage"),
                "minimum": self.MIN_FLEET,
            }
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

        # Re-ask some of the people who WERE inside last time.
        #
        # The fresh sample gives an unbiased headcount but says nothing about
        # whether anyone is getting out: a zone holding 8,000 people looks the
        # same whether they are walking through or trapped. Re-checking a small
        # cohort answers that directly - if most of them are still inside a
        # cycle later, the place is not clearing.
        #
        # Kept small because it is paid for out of the same budget, and it is
        # counted separately so it can never distort the headcount.
        zs = self.zones.get(zone_id)
        cohort = []
        if zs is not None and zs.cohort:
            pool = [h for h in zs.cohort if h not in chosen]
            # Never take more than a fifth of what this cycle was granted -
            # the headcount is the measurement that matters.
            room = max(0, min(self.COHORT_SIZE, max_calls // 5, len(pool)))
            cohort = self._rng.sample(pool, room) if room else []
        inside = checked = unknown = 0
        now_inside: set = set()
        cohort_checked = cohort_left = 0

        for hashed in list(chosen) + list(cohort):
            is_cohort = hashed in cohort
            phone = self.registry.vault.phone_for(hashed)
            if not phone:
                continue
            try:
                r = self.client.verify_location(phone, area, z.district_id)
            except ApiError:
                continue
            # Paid for either way, so the ledger is charged before the answer
            # is examined.
            self.budget.spend(1, self.now)
            res = r["verification_result"]

            # UNKNOWN means the network could not tell, NOT that the person is
            # elsewhere. Counting it in the denominator quietly shrinks every
            # estimate: measured against the live network, 23% of answers come
            # back UNKNOWN, so a crowd of 10,000 was being reported as 7,700 -
            # a 23% under-count of the one number the alarm depends on.
            #
            # It is excluded from both sides instead. The remaining answers are
            # still a fair sample of the people the network CAN see.
            if res == "UNKNOWN":
                if not is_cohort:
                    unknown += 1
                continue

            here = res == "TRUE" or (res == "PARTIAL" and r.get("match_rate", 0) >= 55)
            if is_cohort:
                # Never counted in the headcount - this cohort was chosen
                # BECAUSE they were inside, so including them would inflate it.
                cohort_checked += 1
                if not here:
                    cohort_left += 1
                else:
                    now_inside.add(hashed)
                continue

            checked += 1
            if here:
                inside += 1
                now_inside.add(hashed)

        if unknown and checked:
            share = unknown / (unknown + checked)
            if share >= 0.4:
                # Worth saying out loud: the sample cost full price and came
                # back mostly unusable, so the estimate rests on fewer devices
                # than the cadence intended.
                self.log("thin_sample",
                         f"{share:.0%} of answers for {zone_id[5:]} were UNKNOWN - "
                         f"the estimate rests on {checked} devices, not {checked + unknown}",
                         zone=zone_id)

        people = self.registry.people_from_panel(inside, checked, self.city.population)

        # What the cohort revealed, measured against what free movement would
        # have given over the SAME stretch of time.
        #
        # A raw fraction is meaningless on its own. A zone is 600 m across and
        # takes about fifteen minutes to walk, so over a one-minute gap barely
        # any of a cohort should have left even when everybody is strolling
        # through unobstructed. Compared against a flat 30% that read as "not
        # clearing" every single time, and the rule fired on calm evenings.
        #
        # So this is a RATIO: 1.0 means people are leaving exactly as fast as
        # unobstructed walking would take them, and 0.2 means five times slower
        # than they should be, which is what being stuck actually looks like.
        outflow = None
        # Eight answers minimum. With fewer, one person's phone failing to
        # answer swings the ratio far enough to invent a blockage.
        if cohort_checked >= 6 and zs is not None:
            elapsed = max(self.now - zs.cohort_at, 1.0)
            free_time = max(self.city.free_crossing_time_s(zone_id), 1.0)
            expected = min(0.95, max(elapsed / free_time, 0.01))
            outflow = (cohort_left / cohort_checked) / expected
        dwell = None
        if zs is not None:
            for h in now_inside:
                zs.inside_first_seen.setdefault(h, self.now)
            # Anybody no longer inside stops accumulating dwell.
            for h in list(zs.inside_first_seen):
                if h not in now_inside and h not in zs.cohort:
                    zs.inside_first_seen.pop(h, None)
            if len(now_inside) >= K_ANON_MIN:
                ages = sorted(self.now - zs.inside_first_seen.get(h, self.now)
                              for h in now_inside)
                median_age = ages[len(ages) // 2]
                free_time = self.city.free_crossing_time_s(zone_id)
                if median_age > 0 and free_time > 0:
                    dwell = median_age / free_time
            zs.cohort = now_inside
            zs.cohort_at = self.now

        return people, inside, checked, outflow, dwell

    # How many coordinate fixes to buy when an alarm is about to be raised.
    # Retrieval costs about three times a verification, so this is deliberately
    # small and only ever spent at the moment something fires.
    POSITION_FIXES = 20
    # Below this many usable fixes the answer is not worth reporting.
    POSITION_MIN_FIXES = 6

    def locate_crowd(self, zone_id: str) -> dict | None:
        """
        Ask where inside the zone the crowd is actually standing.

        WHY THIS EXISTS. Counting tells you how many people are in a 600 m
        circle; it cannot tell you whereabouts. Those are very different
        situations: eighteen thousand people seated in a stadium bowl and
        eighteen thousand crushed against an exit ramp produce an identical
        headcount and an identical "nobody is leaving", and only one of them is
        an emergency.

        WHY IT CAN WORK AT ALL. Positioning error is 150-400 m and the ramp is
        147 m long, so a fix cannot be resolved onto the ramp itself. But the
        bowl and the ramp are roughly 700 m apart, which is larger than the
        error - so telling those two places apart is a question the network CAN
        answer, even though locating either one precisely is not.

        WHAT IT NEVER DOES. It never cancels an alarm. Suppressing a warning is
        the most dangerous thing this system could do - a mistake there is a
        missed crush rather than an irritated operator - and a median position
        drawn from twenty noisy fixes is nowhere near strong enough evidence to
        overrule the arithmetic. The result is attached to the verdict as a
        note, and a person decides what it means.
        """
        zs = self.zones.get(zone_id)
        hazard = self.city.bottleneck_of(zone_id)
        if zs is None or hazard is None or not zs.cohort:
            return None

        z = self.city.zones[zone_id]
        sample = list(zs.cohort)
        if len(sample) > self.POSITION_FIXES:
            sample = self._rng.sample(sample, self.POSITION_FIXES)

        lats: list[float] = []
        lons: list[float] = []
        for hashed in sample:
            phone = self.registry.vault.phone_for(hashed)
            if not phone:
                continue
            try:
                r = self.client.retrieve_location(phone, 120, z.district_id)
            except ApiError:
                continue
            self.budget.spend(3, self.now)
            if r.get("status") != "OK":
                continue
            lats.append(float(r["latitude"]))
            lons.append(float(r["longitude"]))

        if len(lats) < self.POSITION_MIN_FIXES:
            # Not enough to say anything. Reported as unknown rather than as
            # reassurance - the alarm is unaffected either way.
            return {"fixes": len(lats), "known": False}

        # Median, not mean. A couple of wild fixes are normal and an average
        # would be dragged off by them.
        lats.sort()
        lons.sort()
        mid = LatLon(lats[len(lats) // 2], lons[len(lons) // 2])
        # The middle of the narrow link, which is the place that matters.
        hz = hazard.points[len(hazard.points) // 2]
        distance = mid.meters_to(hz)

        # How spread out the fixes are. A wide spread usually means the crowd is
        # in two places at once - streaming from one to the other - and then the
        # median sits between them and describes neither.
        spread = sum(mid.meters_to(LatLon(la, lo))
                     for la, lo in zip(lats, lons)) / len(lats)

        return {
            "fixes": len(lats), "known": True,
            "metres_from_hazard": round(distance),
            "spread_m": round(spread),
            "at_the_hazard": distance <= 450,
        }

    # ---- the tick ------------------------------------------------------

    def tick(self, now: float | None = None) -> list[Verdict]:
        self.now = time.time() if now is None else now
        self._prune()

        scheduled = self._scheduled_zones()
        shares = self._congestion_signal()
        vals = sorted(shares.values())
        # Districts absent from `shares` are the untrusted ones. They cannot
        # set the baseline and cannot ask for money, but they are logged once
        # so the gap is visible rather than silent.
        untrusted = [d for d in self.districts if d not in shares]
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
        city_wide = (bool(shares) and all(v > 0.35 for v in shares.values())
                     and len(shares) > 1)

        # 1. Which zones deserve paid attention?
        wanted: list[Request] = []
        for zid, zs in self.zones.items():
            did = zs.district_id
            if did not in shares:
                # Not enough devices there to justify spending on a guess.
                continue
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
            zs.next_interval = interval
            # Congestion is free and arrives early. Treating it as a reason to
            # look more closely — rather than waiting until a rate has already
            # been measured — is what buys the warning time.
            if state == IDLE and (zid in scheduled or zs.rate_per_min() > 0 or share >= 0.20):
                interval, sample = self.CADENCE[WATCHING]
                zs.next_interval = interval
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

        if untrusted:
            self.log("coverage",
                     f"not enough devices to judge {', '.join(d[9:] for d in untrusted)} "
                     f"- reported as no coverage, not as calm",
                     districts=untrusted)
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

            people, inside, checked, outflow, dwell = self.count_zone(
                req.zone_id, allowed)
            if checked == 0:
                continue
            # Use the interval this zone actually asked for, not the one its
            # district's state implies.
            #
            # The two disagree exactly when it matters. A zone that looks busy
            # raises its own cadence to 90 s, but the district is still IDLE on
            # the cycle that discovers it - so the next check was being booked
            # 300 s away. Worse, the district's state is only updated at the
            # END of this loop, so the value read here is always one cycle
            # stale. The first three counts landed five minutes apart during a
            # situation the engine had already judged unusual, and most of the
            # available warning time was spent waiting.
            state_now = ALERT if zs.alerted else self.districts[req.district_id].state
            by_state = self.CADENCE.get(state_now, (300.0, 18))[0]
            zs.next_check_at = self.now + min(zs.next_interval or by_state, by_state)
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
                outflow_ratio=outflow, dwell_ratio=dwell,
                above_baseline=(None if not zs.baseline
                                else people / max(zs.baseline, 1.0)),
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

            # Learn what quiet looks like here - but only while quiet.
            #
            # Updated after the verdict and only when no alarm is live, so a
            # long incident cannot slowly teach the zone that a crush is
            # normal. Slow on purpose: one busy evening should barely move it.
            if not zs.alerted and not v.dangerous:
                zs.baseline = (people if zs.baseline is None
                               else zs.baseline * 0.9 + people * 0.1)

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
                    # Buy coordinates once, at the moment of firing, to say
                    # whereabouts in the circle these people are. This informs
                    # the alarm; it never withholds it.
                    where = self.locate_crowd(req.zone_id)
                    note = None
                    if where and where.get("known"):
                        d = where["metres_from_hazard"]
                        if where["at_the_hazard"]:
                            note = (f"position confirms it: the crowd is about "
                                    f"{d} m from {v.hazard_label}")
                        elif where["spread_m"] > 400:
                            note = (f"the crowd is spread over about "
                                    f"{where['spread_m']} m and its middle sits "
                                    f"{d} m from {v.hazard_label} - it may be "
                                    f"moving toward the link rather than held at it")
                        else:
                            note = (f"position suggests these people are about "
                                    f"{d} m from {v.hazard_label}, so they may be "
                                    f"gathered elsewhere in the zone rather than "
                                    f"held at it - treat the size as real and the "
                                    f"location as uncertain")
                    elif where is not None:
                        note = (f"position could not be established "
                                f"({where['fixes']} usable fixes) - the alarm "
                                f"stands on the measurement alone")
                    # WHERE the middle of this crowd sits, and nothing more.
                    #
                    # This deliberately does NOT claim which alarms are real.
                    # Tested against a full evening it got that backwards: the
                    # genuine crowd was strung out along a 631 m approach walk
                    # so its midpoint landed 459 m from the ramp, while two
                    # false alarms on residential districts sat neatly around
                    # their own crossings and looked pinpoint accurate.
                    #
                    # Had this been allowed to silence anything, it would have
                    # silenced the one crowd that mattered and kept both of the
                    # others. It is reported as a measurement for an operator
                    # to weigh, never as a verdict.
                    if where and where.get("known"):
                        shape = ("at_the_link" if where["at_the_hazard"]
                                 else "spread_out")
                    else:
                        shape = "not_located"
                    record = {"t": self.now, **v.to_dict(),
                              "where": where, "position_note": note,
                              "crowd_shape": shape}
                    self.alerts.append(record)
                    if len(self.alerts) > self.MAX_ALERTS:
                        del self.alerts[:-self.MAX_ALERTS]
                    self.log("alert", f"{v.hazard_label}: {v.reason}",
                             crowd_shape=shape, **v.to_dict())
                    if note:
                        self.log("position", note, zone=req.zone_id, **(where or {}))
                    self._notify(self.on_alert_raised, record)
                ds.state = ALERT
            else:
                # Two readings in a row before standing down, exactly as two
                # are required before firing.
                #
                # A single low reading used to clear the alarm, and a single
                # high one re-raised it. Since each sampled device stands for
                # hundreds of people the measured rate wobbles around zero at
                # the end of an event, so one crowd raised three separate
                # alarms in an hour - and every one of them wrote a fresh
                # incident and sent a fresh warning to everybody in the
                # district. The result was a flood of notifications for a
                # single crowd, which is exactly how people learn to ignore
                # them.
                zs.consecutive_low = zs.consecutive_low + 1 if rate <= 0 else 0
                if zs.alerted and zs.consecutive_low >= 2:
                    zs.alerted = False
                    zs.consecutive_low = 0
                    # Why it ended, in the same numbers that made it start.
                    #
                    # An alarm that simply vanishes teaches people to distrust
                    # the next one - they never learn whether the danger passed
                    # or the system gave up. The figures that raised it are the
                    # figures that should retire it.
                    why = {
                        "people": round(v.people_low / 0.7) if v.people_low else 0,
                        "falling_by": round(abs(rate)),
                        "capacity_per_min": round(capacity),
                        "width_m": v.hazard_width_m,
                        "segment_label": v.hazard_label,
                    }
                    self.log("standdown",
                             f"{v.hazard_label} is clearing: about "
                             f"{why['people']:,} people left and the number is "
                             f"falling by {why['falling_by']:,}/min, so the "
                             f"{v.hazard_width_m:.0f} m link is passing people "
                             f"faster than they arrive",
                             zone=req.zone_id, **why)
                    self._notify(self.on_alert_cleared, req.zone_id, self.now, why)
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
