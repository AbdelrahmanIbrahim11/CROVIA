"""
Where a device is, and who is allowed to decide that.

These exist because of a defect that produced no error and no wrong-looking
number. Devices were dealt into four district piles by position in a shuffled
list, and that guess was written down and used exactly as if it had been
measured. Every congestion notification was attributed to it, and the share
that decides which district deserves paid attention was computed from it.

The rule these tests hold down is one sentence: only the network may say where
a device is.

    PYTHONPATH=. ./venv/bin/python tests/test_placement.py
"""

from __future__ import annotations

import sys

from app.core.city import city
from app.core.registry import DeviceRegistry
from app.camara.client import SimulatorClient
from app.core.budget import Budget
from app.detect.engine import Engine

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"  {'pass' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def fresh() -> Engine:
    return Engine(city, SimulatorClient(), DeviceRegistry(), Budget(per_hour=6000))


def fill(engine: Engine, district: str, n: int, busy: int = 0) -> None:
    """Place n devices in a district, `busy` of them reporting congestion."""
    for i in range(n):
        h = engine.registry.add_sentinel(f"+9745{district[:3]}{i:05d}")
        engine.registry.place(h, district, 0.0)
        if i < busy:
            engine.districts[district].high_devices[h] = 0.0


# ---------------------------------------------------------------------------
# Only the network places a device
# ---------------------------------------------------------------------------

def test_enrolling_does_not_place_a_device():
    r = DeviceRegistry()
    h = r.add_sentinel("+97430000001")
    check("a new sentinel is in no district", r.district_of(h) is None)
    check("and in no district's fleet",
          all(not r.fleet(d) for d in city.districts))


def test_a_declared_district_is_ignored():
    """The sign-up hint must not place anybody. This is the original defect."""
    r = DeviceRegistry()
    h = r.add_sentinel("+97430000002", "district_stadium")
    check("a declared district does not place the device",
          r.district_of(h) is None, "only a geofence notification may")


def test_a_geofence_notification_places_a_device():
    e = fresh()
    h = e.registry.add_sentinel("+97430000003")
    e.registry.bind_subscription("sub-1", h, "district", "district_stadium")
    e.on_geofence("sub-1", "area-entered")
    check("a geofence notification places it",
          e.registry.district_of(h) == "district_stadium")


def test_entering_a_new_district_leaves_the_old_one():
    e = fresh()
    h = e.registry.add_sentinel("+97430000004")
    e.registry.bind_subscription("sub-a", h, "district", "district_central")
    e.registry.bind_subscription("sub-b", h, "district", "district_stadium")
    e.on_geofence("sub-a", "area-entered")
    e.on_geofence("sub-b", "area-entered")
    check("it moved to the new district",
          e.registry.district_of(h) == "district_stadium")
    check("and is no longer in the old one",
          h not in e.registry.fleet("district_central"),
          "so a device is never counted in two places")


# ---------------------------------------------------------------------------
# A district nobody is watching is not a calm district
# ---------------------------------------------------------------------------

def test_an_empty_district_has_no_share():
    e = fresh()
    fill(e, "district_stadium", 60, busy=6)
    shares = e._congestion_signal()
    check("the watched district has a share", "district_stadium" in shares)
    check("the empty ones have none at all",
          "district_marina" not in shares,
          "absent, not zero - zero is a claim we cannot make")


def test_an_empty_district_cannot_become_the_baseline():
    """
    The regression this file exists for.

    The baseline is the quietest district, and everything else is judged
    against it. An empty district reported a share of exactly zero, so it
    became the yardstick for the whole city.
    """
    e = fresh()
    fill(e, "district_stadium", 60, busy=6)      # share 0.10
    fill(e, "district_central", 60, busy=3)      # share 0.05
    # marina and foxhills left empty
    shares = e._congestion_signal()
    baseline = min(shares.values())
    check("the baseline comes from a watched district",
          baseline == 0.05, f"baseline={baseline}")
    check("not from an empty one", 0.0 not in shares.values())


def test_a_thin_district_cannot_trigger_spending():
    e = fresh()
    # Four devices, one busy: a share of 0.25, which clears the strongest
    # trigger on its own. It must not be believed.
    fill(e, "district_marina", 4, busy=1)
    before = e.ledger.total
    e.tick(1000.0)
    check("a 4-device district spends nothing",
          e.ledger.total == before, f"{e.ledger.total - before} calls")
    check("and is reported as a coverage gap",
          any(t["kind"] == "coverage" for t in e.trace))


def test_coverage_names_each_district_honestly():
    e = fresh()
    fill(e, "district_stadium", 60)
    fill(e, "district_marina", 6)
    cov = e.coverage()
    check("a watched district says watched",
          cov["district_stadium"]["state"] == "watched")
    check("a thin one says thin coverage",
          cov["district_marina"]["state"] == "thin coverage",
          f"{cov['district_marina']['devices']} devices")
    check("an empty one says no coverage",
          cov["district_foxhills"]["state"] == "no coverage")
    check("none of them is described as calm",
          all(c["state"] != "calm" for c in cov.values()))


# ---------------------------------------------------------------------------
# Enrolment assigns no district at all
# ---------------------------------------------------------------------------

def test_auto_enrol_takes_no_district_argument():
    import inspect
    from app.services import enrollment
    params = inspect.signature(enrollment.auto_enrol_users).parameters
    check("sentinels_per_district is gone", "sentinels_per_district" not in params)
    check("the districts list is gone", "districts" not in params,
          "nothing here chooses a district any more")


def run() -> int:
    print("\n-- only the network places a device ------------------------------")
    test_enrolling_does_not_place_a_device()
    test_a_declared_district_is_ignored()
    test_a_geofence_notification_places_a_device()
    test_entering_a_new_district_leaves_the_old_one()

    print("\n-- an unwatched district is not a calm one -----------------------")
    test_an_empty_district_has_no_share()
    test_an_empty_district_cannot_become_the_baseline()
    test_a_thin_district_cannot_trigger_spending()
    test_coverage_names_each_district_honestly()

    print("\n-- enrolment assigns nothing -------------------------------------")
    test_auto_enrol_takes_no_district_argument()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAILED: {name} {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(run())
