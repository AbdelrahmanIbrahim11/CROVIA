"""
Run every unit test and print one summary.

    PYTHONPATH=. ./venv/bin/python tests/run_all.py

These check the rules ONE AT A TIME, in isolation: the capacity arithmetic, who
is allowed to read what, whether a warning nags. No network, no database, no
Nokia key - so they run anywhere in a few seconds and a failure points at a
single rule rather than somewhere in a whole evening.

For the other kind of test - a complete evening in a simulated Lusail, judged
end to end - see scenario/run_all.py. The two answer different questions and
neither replaces the other.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Each suite runs in its OWN process, not imported into this one.
#
# They are not independent inside a single interpreter: each sets its own
# DATABASE_URL and builds its own tables at import time, so whichever runs
# first wins and the rest quietly share its database. Imported together, a
# suite that expects two warnings found five left behind by an earlier file and
# failed - a false failure caused entirely by the runner.
SUITES = [
    ("test_logic", "the danger rules: capacity, the three alarm paths"),
    ("test_auth", "who may see and do what"),
    ("test_placement", "only the network may say where a device is"),
    ("test_warning_lifecycle", "warnings start, end, and do not nag"),
    ("test_demo", "the demonstration endpoints"),
]


def run_one(name: str) -> tuple[int, int, str]:
    """Run one suite and read its score out of what it printed."""
    env = dict(os.environ, PYTHONPATH=ROOT)
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, f"{name}.py")],
                           capture_output=True, text=True, timeout=900, env=env)
    except subprocess.TimeoutExpired:
        return 0, 0, "timed out"
    out = r.stdout + r.stderr
    for line in reversed(out.splitlines()):
        if "passed" in line and "/" in line:
            try:
                got, total = line.split()[0].split("/")
                return int(got), int(total), out
            except ValueError:
                continue
    return 0, 0, out


def main() -> int:
    print("=" * 72)
    print("CROVIA - unit tests")
    print("Each one checks a single rule. For a whole simulated evening,")
    print("run scenario/run_all.py instead.")
    print("=" * 72)

    t0 = time.time()
    total_passed = total_all = 0
    failures: list[tuple[str, str]] = []

    for name, what in SUITES:
        got, total, out = run_one(name)
        total_passed += got
        total_all += total
        mark = "ok  " if total and got == total else "FAIL"
        print(f"  {mark}  {name:<26} {got:>3}/{total:<3}  {what}")
        if not total or got != total:
            failures.append((name, out))

    print("-" * 72)
    print(f"  {total_passed}/{total_all} checks passed in {time.time() - t0:.1f}s")

    for name, out in failures:
        print(f"\n--- {name} ---")
        for line in out.splitlines():
            if "FAIL" in line:
                print(f"   {line.strip()}")

    print()
    return 0 if total_all and total_passed == total_all else 1


if __name__ == "__main__":
    sys.exit(main())
