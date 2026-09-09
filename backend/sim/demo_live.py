"""
Watch the whole system work on a real crowd.

Runs the twin, drives the real engine and the real agent, and prints what the
agent decides and what the rules judge. Every number comes from the same code
paths the server uses; only the network underneath is simulated, because the
Nokia sandbox cannot move a device.
"""
from __future__ import annotations

import sys

from app.ai import graph as ai
from app.camara.client import Area, ApiError
from app.core.budget import Budget
from app.core.city import city
from app.core.registry import DeviceRegistry
from app.detect.engine import Engine, ScheduledEvent
from sim.camara_twin import TwinCamaraClient
from sim.twin import Event, Population, Twin

import numpy as np

ZONE = "zone_stadium_north_concourse"


def main() -> None:
    twin = Twin(city, Population(), [Event(ZONE, 12_000, duration_s=12 * 60, label="match")])
    client = TwinCamaraClient(twin)
    registry = DeviceRegistry()
    engine = Engine(city, client, registry, Budget(per_hour=6000))
    engine.add_scheduled(ScheduledEvent(ZONE, 0.0, 12_000, duration_s=12 * 60, label="match"))

    rng = np.random.default_rng(3)
    app_idx = np.where(twin.has_app)[0]
    by_d = {d: [] for d in city.districts}
    for i in app_idx:
        by_d[twin.home_district[i]].append(int(i))
    phone = lambda i: f"+974{30000000 + i}"

    for did, mem in by_d.items():
        rng.shuffle(mem)
        for i in mem[:60]:
            p = phone(i); client.bind(p, i); h = registry.add_sentinel(p, did)
            try:
                sub = client.create_congestion_subscription(p, "x", 86400)
                registry.bind_subscription(sub, h, "congestion", did)
                d = city.districts[did]
                g, evt = client.create_geofence_subscription(
                    p, did, Area(d.center.lat, d.center.lon, d.radius_m), "x", 86400, True)
                registry.bind_subscription(g, h, "district", did)
                if evt and evt["type"] == "area-entered":
                    registry.place(h, did, 0.0)
            except ApiError:
                pass
    for i in rng.choice(app_idx, size=400, replace=False):
        p = phone(int(i)); client.bind(p, int(i)); registry.add_panel(p, twin.home_district[int(i)])

    print(f"policy: {ai.build_policy().name}")
    print(f"{len(registry.sentinels)} devices monitored, {registry.panel_size()} of them the panel")
    print(f"{ZONE[5:]}: narrowest link {city.bottleneck_of(ZONE).width_m:.0f} m, "
          f"passes {city.zone_capacity_per_min(ZONE):,.0f} people/min\n")
    print(f"{'time':>6} {'true in zone':>13} {'estimate':>9} {'fill/min':>9} {'spend':>6}  what happened")
    print("-" * 108)

    fired = False
    for step in range(int(40 * 60 / 5)):
        snap = twin.step()
        now = twin.t
        for ev in client.tick(now):
            if ev["type"] == "congestion":
                engine.on_congestion(ev["subscriptionId"], ev["congestionLevel"],
                                     ev["confidenceLevel"])
            else:
                engine.on_geofence(ev["subscriptionId"], ev["type"])

        if step % 6 == 0:
            engine.tick(now)
        if step % 24 == 0:
            decisions = ai.run_once(engine)
            zs = engine.zones[ZONE]
            est = round(zs.counts[-1][1]) if zs.counts else 0
            note = ""
            for d in decisions:
                if d["zone"] == ZONE:
                    note = f"{d['action']} ({d.get('calls_spent',0)} calls) - {d['reasoning'][:56]}"
                    break
            if engine.alerts and not fired:
                fired = True
                a = engine.alerts[0]
                note = f"** ALERT ** {a['segment_label']}: {a['reason'][:62]}"
            print(f"{now:6.0f} {twin.people_in_zone(ZONE):13,} {est:9,} "
                  f"{zs.rate_per_min():9,.0f} {engine.ledger.total:6,}  {note}")

    print("-" * 108)
    if engine.alerts:
        a = engine.alerts[0]
        crit = next((h["t"] for h in twin.history
                     if h["zones"][ZONE]["worst_density"] >= 4.0), None)
        print(f"\nALARM at t={a['t']:.0f}s on {a['segment_label']}")
        print(f"  {a['reason']}")
        print(f"  estimate {a['people_low']:,.0f}-{a['people_high']:,.0f} people")
        if crit:
            print(f"  it became genuinely dangerous at t={crit:.0f}s "
                  f"-> warned {(crit - a['t'])/60:+.1f} minutes ahead")
    else:
        print("\nno alarm raised")
    print(f"\ntotal API calls: {engine.ledger.total:,}  {engine.ledger.summary()['by_tier']}")


if __name__ == "__main__":
    main()
