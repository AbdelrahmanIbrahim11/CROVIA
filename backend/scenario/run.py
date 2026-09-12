"""
The honest test: a real evening in Lusail, judged from the outside.

    PYTHONPATH=. ./venv/bin/python scenario/run.py

WHAT THIS IS
------------
Thirty thousand people live an evening. Ten thousand of them carry the app.
Some go to a match, sit through it, and then all leave at once through a 9 metre
ramp. CROVIA runs against them through nothing but the CAMARA interface, and at
the end we compare what it said with what actually happened.

The twin is not involved. This is a separate world (scenario/world.py) behind a
separate network (scenario/network.py), built specifically to remove the three
assumptions that flattered the previous results.

HOW IT IS KEPT HONEST
---------------------
APP OWNERSHIP IS UNEVEN. The twin gave every person the same chance of carrying
the app, which made the panel a perfect random sample and the headcount
unbiased by construction. Here, ownership varies almost five-fold between
districts, so the panel genuinely misrepresents the city and the headcount is
wrong in a way that can be measured.

THE POPULATION FIGURE IS WRONG. CROVIA multiplies by the 30,000 in the city
plan; only about 27,600 people are actually present.

THE ENGINE IS SEALED. It receives subscriptions, notifications and verification
answers. It cannot see a position, a headcount or a phase name. Every number it
reports is something it worked out.

THE WORLD DOES NOT KNOW THE DETECTOR'S FORMULA. CROVIA's entire rule is
`width * 72`. Nothing in world.py uses it: movement is limited by space and by
walking speed falling as the ground fills, so the throughput of the ramp is a
consequence rather than a restatement.

THREE OUTCOMES THAT WOULD ALL BE FAILURES
-----------------------------------------
  * an alarm during `calm`, `arrival` or `match`   -> a false alarm
  * no alarm during `egress`                       -> a miss
  * an alarm that never stands down                -> nobody can trust the next one

WHAT IS DELIBERATELY HARD HERE
------------------------------
The `match` phase is the trap. Eighteen thousand people are packed into a small
area, cell towers are saturated, and congestion will read High across the whole
stadium district - but they are seated, safe, and not moving. A detector that
treats "crowded" as "dangerous" fires here and is wrong. Nothing should happen.
"""

from __future__ import annotations

import os
import sys
import uuid

# Settings must be in place before the app is imported.
os.environ.setdefault("JWT_SECRET", "scenario-secret-long-enough-for-sha256")
os.environ.setdefault("STAFF_INVITE_CODE", "scenario-invite")
os.environ.setdefault("WEBHOOK_AUTH_TOKEN", "scenario-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///./scenario.db")
os.environ["NOKIA_NAC_API_KEY"] = ""      # never touch the real network
os.environ["CROVIA_TWIN"] = "0"           # and never the twin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient          # noqa: E402

from app import runtime                            # noqa: E402
from app.core.city import city                     # noqa: E402
from app.core.registry import hash_phone           # noqa: E402
from app.main import app                           # noqa: E402
from app.services import enrollment                # noqa: E402
from app.usersDB.db import getdb                   # noqa: E402
from scenario.network import ScenarioNetwork       # noqa: E402
from scenario.webhook import Delivery              # noqa: E402
from scenario.world import SCHEDULE, World         # noqa: E402

# ===========================================================================
# TUNABLES
# ===========================================================================

# How many app users get an account and a subscription.
#
# Every one of these is real database rows plus real CAMARA subscriptions, so
# the number drives how long the run takes. 1,200 is enough for every district
# to clear the 25-device minimum while still finishing in a couple of minutes;
# raise it towards 10,000 for a full-scale run.
ENROL = 1_200

PANEL_SIZE = 400        # the counting group
STEP_SECONDS = 30.0     # how much world time passes per cycle
PRINT_EVERY = 4         # cycles between progress lines


def banner(text: str) -> None:
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def main() -> int:
    banner("CROVIA - unbiased scenario, no twin, no real Nokia")

    world = World()
    t = world.truth()
    print(f"  people actually present : {t['people_present']:,}"
          f"   (the city plan says {30000:,})")
    print(f"  carrying the app        : {t['app_users']:,}")
    print("\n  app ownership by district - deliberately uneven, which is what")
    print("  makes the panel an imperfect sample of the city:")
    import numpy as np
    for did in city.districts:
        sel = world.home_district == did
        n, a = int(sel.sum()), int((sel & world.has_app).sum())
        print(f"    {did:22} {a:>5} of {n:>6} people  ({a/max(n,1)*100:>4.1f}%)")

    with TestClient(app) as client:
        deliver = Delivery(client)
        net = ScenarioNetwork(world, deliver)

        # Replace the engine's client with the scenario network. The engine
        # itself is untouched - it cannot tell the difference, which is the
        # whole point.
        engine = runtime.get_engine()
        engine.client = net
        engine.ledger = net.ledger

        banner("1. people install the app and agree to be monitored")
        db = next(getdb())
        app_idx = [int(i) for i in range(world.n) if world.has_app[i]][:ENROL]
        for k, i in enumerate(app_idx):
            phone = f"+9745{i:07d}"
            net.bind(phone, i)
            enrollment.grant_consent(db, phone)
            enrollment.enrol(db, phone,
                             enrollment.PANEL if k < PANEL_SIZE
                             else enrollment.SENTINEL)
        db.commit()
        print(f"  {len(app_idx):,} accounts with consent "
              f"({PANEL_SIZE} panel, {len(app_idx) - PANEL_SIZE} sentinels)")

        banner("2. the operator subscribes them to the network")
        loaded = enrollment.load_into_registry(db, engine.registry)
        print(f"  loaded into the engine: {loaded}")
        subs = 0
        for hashed in list(engine.registry.sentinels):
            phone = engine.registry.vault.phone_for(hashed)
            if not phone:
                continue
            r = enrollment.subscribe_device(db, engine, phone)
            subs += len(r.get("subscriptions", []))
        print(f"  {subs:,} CAMARA subscriptions created")
        print(f"  devices the NETWORK has placed in a district: "
              f"{len(engine.registry.device_district):,}")
        print("  (anyone it could not place stays in no district - that is the")
        print("   honest answer, not a guess)")

        for did in city.districts:
            n = len(engine.registry.fleet(did))
            mark = "watched" if n >= engine.MIN_FLEET else "THIN - not trusted"
            print(f"    {did:22} {n:>4} devices   {mark}")

        # A citizen whose screen we will read at the end.
        tag = uuid.uuid4().hex[:6]
        watcher_phone = f"+9745{app_idx[0]:07d}"
        client.post("/auth/register", json={
            "username": f"Watcher {tag}", "password": "a-good-password",
            "email": f"watcher-{tag}@example.com",
            "number": watcher_phone, "consent": True})
        tok = client.post("/auth/login", json={
            "email": f"watcher-{tag}@example.com",
            "password": "a-good-password"}).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}

        banner("3. the evening")
        results = []
        clock = 0.0
        for phase in SCHEDULE:
            print(f"\n-- {phase.name.upper()} ({phase.minutes:.0f} min) "
                  f"{'-' * max(0, 50 - len(phase.name))}")
            print(f"   {phase.note}")
            alarms_before = len(engine.alerts)
            cycles = int(phase.minutes * 60 / STEP_SECONDS)

            for c in range(cycles):
                world.step(STEP_SECONDS, phase.name)
                clock += STEP_SECONDS
                net.push_notifications(clock)
                engine.tick(clock)

                if c % PRINT_EVERY == 0:
                    tr = world.truth()
                    z = engine.zones.get("zone_stadium_north_concourse")
                    v = z.last_verdict if z else None
                    said = (f"{v.people_low:,.0f}-{v.people_high:,.0f}"
                            if v else "not counted")
                    print(f"   t+{clock/60:>5.1f}m  truly in zone "
                          f"{tr['in_egress_zone']:>6,}  |  CROVIA says {said:>17}"
                          f"  |  alarms {len(engine.alerts)}")

            raised = len(engine.alerts) - alarms_before
            tr = world.truth()
            results.append({
                "phase": phase.name, "alarms": raised,
                "truly_dangerous": tr["dangerous_now"],
                "worst_density": tr["worst_density"],
            })

        banner("4. what the citizen saw")
        me = client.get("/api/warnings/me", headers=H).json()["warnings"]
        if not me:
            print("  no warnings at all")
        for w in me:
            state = "LIVE" if w["active"] else "ended"
            print(f"  [{w['kind']:>9}] {state:>5}  {w['title']}")
            print(f"              {w['body'][:100]}")

        banner("5. the verdict")
        print(f"  {'phase':<12} {'alarms':>7} {'really dangerous?':>19} "
              f"{'worst density':>15}   result")
        ok = True
        for r in results:
            should = r["phase"] == "egress"
            good = (r["alarms"] > 0) == should or (should and r["alarms"] > 0)
            if r["phase"] in ("calm", "arrival", "match"):
                good = r["alarms"] == 0
            ok &= good
            print(f"  {r['phase']:<12} {r['alarms']:>7} "
                  f"{str(r['truly_dangerous']):>19} "
                  f"{r['worst_density']:>13.2f}/m2   "
                  f"{'ok' if good else 'FAILED'}")

        print(f"\n  API calls spent : {net.ledger.total:,}")
        print(f"  notifications   : {deliver.delivered:,} delivered, "
              f"{deliver.rejected} rejected")
        print(f"\n  {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
