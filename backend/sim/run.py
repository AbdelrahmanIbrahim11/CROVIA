"""
Run a scenario end to end against the REAL detection engine, and score it.

Ground truth is read only here, for scoring. The engine sees nothing but the
mocked CAMARA layer.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from dataclasses import asdict, dataclass, field

import copy
from dataclasses import replace

import numpy as np

from app.camara.client import ApiError, Area
from app.core.budget import Budget
from app.core.city import City, city as default_city
from app.core.registry import DeviceRegistry
from app.detect.engine import Engine, ScheduledEvent
from sim.camara_twin import TwinCamaraClient
from sim.scenarios import Scenario, all_scenarios
from sim.twin import Twin

RHO_CRITICAL = 4.0
SINK = "https://example.invalid/webhooks"


@dataclass
class ZoneResult:
    zone_id: str
    expected_danger: bool
    detected: bool = False
    alert_t: float | None = None
    true_critical_t: float | None = None
    lead_s: float | None = None
    peak_true_density: float = 0.0
    peak_true_people: int = 0
    people_est_at_alert: float | None = None
    people_true_at_alert: int | None = None
    count_error_pct: float | None = None
    hazard_segment: str | None = None
    true_worst_segment: str | None = None
    segment_correct: bool | None = None
    unresolved_ticks: int = 0


@dataclass
class RunResult:
    key: str
    title: str
    zones: dict = field(default_factory=dict)
    calls_total: int = 0
    calls_by_tier: dict = field(default_factory=dict)
    calls_by_district: dict = field(default_factory=dict)
    naive_calls: int = 0
    errors: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    allocations: list = field(default_factory=list)
    predictions: list = field(default_factory=list)


def _city_for(sc: Scenario, base: City) -> City:
    """
    Apply the scenario's gate widening to the CITY, not only to the twin.

    Opening extra gates changes the place itself, so the detection engine has
    to see the new width too. Scaling it only inside the twin let the engine
    keep believing a widened 27 m link was still 9 m, so it compared arrivals
    against a capacity three times too small and raised an alarm on a perfectly
    safe egress.
    """
    scale = {e.zone_id: e.width_scale for e in sc.events if e.width_scale != 1.0}
    if not scale:
        return base
    c = copy.copy(base)
    c.segments = dict(base.segments)
    for sid, seg in base.segments.items():
        if seg.zone_id in scale and seg.risk >= 1.4:
            c.segments[sid] = replace(seg, width_m=seg.width_m * scale[seg.zone_id])
    return c


def run(sc: Scenario, city: City = default_city, seed: int = 0,
        keep_trace: bool = True) -> RunResult:
    city = _city_for(sc, city)
    pop = sc.pop
    pop.seed = pop.seed + seed
    twin = Twin(city, pop, sc.events)
    client = TwinCamaraClient(twin, seed=11 + seed,
                              rate_limit_per_min=sc.rate_limit)
    registry = DeviceRegistry()
    budget = Budget(per_hour=sc.budget_per_hour)
    engine = Engine(city, client, registry, budget)
    for ev in sc.events:
        if ev.zone_id in sc.scheduled:
            engine.add_scheduled(ScheduledEvent(
                zone_id=ev.zone_id, starts_at=ev.start_s,
                expected_attendance=ev.n_attendees, duration_s=ev.duration_s,
                label=ev.label or ev.zone_id[5:]))

    rng = np.random.default_rng(99 + seed)
    app_idx = np.where(twin.has_app)[0]

    # --- enrol -----------------------------------------------------------
    # Sentinels are per district and deliberately unbalanced. The panel is a
    # uniform sample of all app users, and only the panel is used for counting.
    by_district: dict[str, list[int]] = {d: [] for d in city.districts}
    for i in app_idx:
        by_district[twin.home_district[i]].append(int(i))

    def phone(i: int) -> str:
        return f"+974{30000000 + int(i)}"

    for did, members in by_district.items():
        rng.shuffle(members)
        for i in members[: sc.sentinels_per_district]:
            p = phone(i)
            client.bind(p, i)
            h = registry.add_sentinel(p, did)
            d = city.districts[did]
            # Transient 5xx responses happen during enrolment too. A device that
            # fails to subscribe is simply left out rather than aborting the run,
            # which is what production has to do as well.
            try:
                sub = client.create_congestion_subscription(p, SINK, 7 * 86400)
                registry.bind_subscription(sub, h, "congestion", did)
            except ApiError:
                pass
            try:
                gsub, evt = client.create_geofence_subscription(
                    p, did, Area(d.center.lat, d.center.lon, d.radius_m), SINK,
                    7 * 86400, initial_event=True)
                registry.bind_subscription(gsub, h, "district", did)
                if evt and evt["type"] == "area-entered":
                    registry.place(h, did, 0.0)
            except ApiError:
                pass

    panel_pick = rng.choice(app_idx, size=min(sc.panel_size, app_idx.size), replace=False)
    for i in panel_pick:
        p = phone(int(i))
        client.bind(p, int(i))
        registry.add_panel(p, twin.home_district[int(i)])

    # --- loop ------------------------------------------------------------
    res = RunResult(key=sc.key, title=sc.title)
    zr = {z: ZoneResult(z, sc.expect.get(z, False)) for z in city.zones}
    steps = int(sc.duration_s / twin.dt)

    for step in range(steps):
        snap = twin.step()
        now = twin.t
        for ev in client.tick(now):
            if ev["type"] == "congestion":
                engine.on_congestion(ev["subscriptionId"], ev["congestionLevel"],
                                     ev["confidenceLevel"])
            else:
                engine.on_geofence(ev["subscriptionId"], ev["type"])

        # The engine only spends every 30 s of simulated time.
        if step % 6 == 0:
            engine.tick(now)

        for zid, z in snap["zones"].items():
            r = zr[zid]
            r.peak_true_density = max(r.peak_true_density, z["worst_density"])
            r.peak_true_people = max(r.peak_true_people, twin.people_in_zone(zid))
            if r.true_critical_t is None and z["worst_density"] >= RHO_CRITICAL:
                r.true_critical_t = now
                r.true_worst_segment = z["worst_segment"]

        for zid, zs in engine.zones.items():
            if zs.unresolved_since:
                zr[zid].unresolved_ticks += 1

    # --- score -----------------------------------------------------------
    for a in engine.alerts:
        r = zr[a["zone_id"]]
        if r.detected:
            continue
        r.detected = True
        r.alert_t = a["t"]
        r.hazard_segment = a["segment"]
        r.people_est_at_alert = (a["people_low"] + a["people_high"]) / 2
        frame = min(twin.history, key=lambda h: abs(h["t"] - a["t"]))
        true_people = frame["zones"][a["zone_id"]]["people"]
        r.people_true_at_alert = true_people
        if true_people > 0:
            r.count_error_pct = (r.people_est_at_alert - true_people) / true_people * 100
        if r.true_critical_t is not None:
            r.lead_s = r.true_critical_t - a["t"]
        if r.true_worst_segment:
            r.segment_correct = (r.hazard_segment == r.true_worst_segment)

    led = client.ledger.summary()
    res.zones = {k: asdict(v) for k, v in zr.items()}
    res.calls_total = led["total"]
    res.calls_by_tier = led["by_tier"]
    res.calls_by_district = led["by_district"]
    res.errors = led["errors"]
    res.naive_calls = int(len(registry.sentinels) * (sc.duration_s / 120.0))
    res.alerts = engine.alerts
    res.allocations = [t for t in engine.trace if t["kind"] == "allocate"]
    res.predictions = engine.predictions
    if keep_trace:
        res.trace = [t for t in engine.trace
                     if t["kind"] in ("alert", "allocate", "unresolved", "suppress", "standdown")][:300]
    return res


def main() -> None:
    seeds = [0, 1, 2]
    out = {"runs": []}
    for sc in all_scenarios():
        for s in seeds:
            fresh = [x for x in all_scenarios() if x.key == sc.key][0]
            r = run(fresh, seed=s)
            rec = asdict(r)
            rec["seed"] = s
            rec["description"] = sc.description
            out["runs"].append(rec)
            watched = {k: v for k, v in r.zones.items()
                       if v["expected_danger"] or v["detected"]}
            bits = []
            for zid, z in watched.items():
                mark = "OK " if z["detected"] == z["expected_danger"] else "BAD"
                lead = "" if z["lead_s"] is None else f" lead={z['lead_s']:+.0f}s"
                bits.append(f"{mark} {zid[5:24]}{lead}")
            print(f"{sc.key:26} seed={s} calls={r.calls_total:5d}  " + " | ".join(bits) or "(silent)",
                  flush=True)
    json.dump(out, open("sim/out_results.json", "w"))
    print("\nwrote sim/out_results.json")


if __name__ == "__main__":
    main()
