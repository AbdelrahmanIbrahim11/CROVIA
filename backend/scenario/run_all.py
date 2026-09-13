"""
Play every scenario several times over and score the result honestly.

    PYTHONPATH=. ./venv/bin/python scenario/run_all.py         # 3 evenings each
    PYTHONPATH=. ./venv/bin/python scenario/run_all.py 5       # 5 evenings each

WHAT THIS IS, AND HOW IT DIFFERS FROM tests/
--------------------------------------------
The unit tests check one rule at a time. This builds a whole evening in Lusail -
about 27,600 people, a match, a crowd leaving through a nine metre ramp - and
asks whether CROVIA got the entire thing right, seeing nothing but the same
CAMARA questions Nokia answers.

Six evenings, three of which MUST NOT raise an alarm. That ratio is deliberate:
a city has perhaps one dangerous evening in twenty, and a suite where half of
them are disasters measures a false-alarm rate that means nothing - yet that
rate is what decides whether an operator ever trusts the system again.

WHY SEVERAL SEEDS
-----------------
One run is an anecdote. The seed changes who lives where, who carries the app,
who goes to the match and exactly how the crowd leaves, so each run is a
genuinely different evening. A rate of "3 out of 3" from one seed repeated
three times would mean no more than "1 out of 1", which is how a perfect score
gets reported by accident.

WHAT IT WILL TELL YOU
---------------------
That detection is strong and the false-alarm rate is not. That is the real
state of the system and it is printed rather than hidden: a suite that only
reports its successes is not evidence of anything.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("JWT_SECRET", "scenario-secret-long-enough-for-sha256")
os.environ.setdefault("DATABASE_URL", "sqlite:///./scenario-run.db")
os.environ["NOKIA_NAC_API_KEY"] = ""      # never touch the real network
os.environ["CROVIA_TWIN"] = "0"           # and never the twin

from app import runtime                                   # noqa: E402
from scenario.catalogue import CATALOGUE                   # noqa: E402

STEP_SECONDS = 30.0


def play(spec, seed: int) -> dict:
    """One evening. Returns what happened, not what we hoped would happen."""
    os.environ["CROVIA_SCENARIO_SEED"] = str(seed)
    runtime.start_demo(source="scenario", scenario=spec.key)
    engine = runtime.get_engine()

    cycles = int(sum(p.minutes for p in spec.schedule) * 60 / STEP_SECONDS)
    peak = 0.0
    first_alarm = danger_at = None

    for _ in range(cycles):
        runtime.step_twin(STEP_SECONDS)
        engine = runtime.get_engine()
        engine.tick(runtime.engine_now())

        truth = runtime._scenario["world"].truth()
        peak = max(peak, truth["worst_density"])
        if truth["dangerous_now"] and danger_at is None:
            danger_at = runtime._scenario["clock"]
        if engine.alerts and first_alarm is None:
            first_alarm = engine.alerts[0]["t"]

    fired = bool(engine.alerts)
    warning_s = (danger_at - first_alarm
                 if first_alarm is not None and danger_at is not None else None)
    runtime.stop_demo()
    return {
        "fired": fired,
        "correct": fired == spec.should_fire,
        "alarms": len(engine.alerts),
        "peak_density": peak,
        "warning_s": warning_s,
    }


def main() -> int:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    print("=" * 78)
    print("CROVIA - full evenings in a simulated Lusail")
    print(f"{len(CATALOGUE)} scenarios x {seeds} seeds = {len(CATALOGUE) * seeds} evenings")
    print()
    print("Nothing here uses the detector's own capacity formula, app ownership")
    print("varies five-fold between districts, and the population figure is")
    print("deliberately wrong - so agreeing with CROVIA is a result, not an echo.")
    print("=" * 78)
    print(f"\n{'scenario':<16}{'seed':>5}{'alarms':>8}{'peak/m2':>9}{'warning':>9}   verdict")
    print("-" * 78)

    t0 = time.time()
    rows: list[tuple] = []
    for spec in CATALOGUE:
        for seed in range(seeds):
            r = play(spec, seed)
            rows.append((spec, r))
            warn = (f"{r['warning_s'] / 60:+.0f} min" if r["warning_s"] is not None
                    else "-")
            print(f"{spec.key:<16}{seed:>5}{r['alarms']:>8}{r['peak_density']:>9.2f}"
                  f"{warn:>9}   {'ok' if r['correct'] else 'FAILED'}")

    print("-" * 78)

    dangerous = [(s, r) for s, r in rows if s.should_fire]
    quiet = [(s, r) for s, r in rows if not s.should_fire]
    caught = sum(1 for _, r in dangerous if r["fired"])
    false_alarms = sum(1 for _, r in quiet if r["fired"])

    print(f"\n  Dangerous evenings caught : {caught}/{len(dangerous)}")
    print(f"  False alarms on quiet ones: {false_alarms}/{len(quiet)}")
    print(f"  Overall as specified      : "
          f"{sum(1 for _, r in rows if r['correct'])}/{len(rows)}")
    print(f"  Ran in {time.time() - t0:.0f}s")

    print("\n  by scenario:")
    for spec in CATALOGUE:
        mine = [r for s, r in rows if s.key == spec.key]
        good = sum(1 for r in mine if r["correct"])
        want = "must fire" if spec.should_fire else "must stay silent"
        print(f"    {spec.key:<16} {good}/{len(mine)}   ({want}) - {spec.title}")

    if false_alarms:
        print(f"\n  The {false_alarms} false alarms are a known limitation, not a")
        print("  surprise: CROVIA can count how many people are inside a 600 m")
        print("  circle but not where inside it they are standing, so a district")
        print("  full of residents who never leave looks like a crowd held at an")
        print("  exit. Removing the rule responsible was measured and made")
        print("  detection four times worse, so it was kept.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
