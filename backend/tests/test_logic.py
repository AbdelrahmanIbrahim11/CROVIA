"""
Tests for the system as it is now.

The previous version of this file tested the pipeline that the current engine
replaced. It had been crashing with an AttributeError for some time, which is
worse than having no test at all: a test suite nobody can run still looks like
one in the repository, and it kept four service modules alive that nothing else
imported.

What is checked here is the reasoning that decides whether people live or die,
plus the two rules that stop the system spending money badly. There is no
network and no database, so it runs anywhere:

    PYTHONPATH=. ./venv/bin/python test_logic.py
"""

from __future__ import annotations

import sys

from app.core.budget import Budget, Request
from app.core.city import city
from app.core.registry import DeviceRegistry
from app.detect.danger import Evidence, assess


# --------------------------------------------------------------------------
# The city plan
# --------------------------------------------------------------------------

def test_capacity_comes_from_width():
    """people/min a link passes = width x 72, and the narrowest link wins."""
    hazard = city.bottleneck_of("zone_stadium_north_concourse")
    assert hazard.width_m == 9.0, hazard.width_m
    assert round(city.zone_capacity_per_min("zone_stadium_north_concourse")) == 648

    # The narrowest link in the zone, not the first or the average.
    for seg in city.segments.values():
        if seg.zone_id == "zone_stadium_north_concourse":
            assert seg.width_m >= hazard.width_m


def test_no_zone_is_smaller_than_nokia_allows():
    """Below 600 m geofence events are unreliable, so nothing may be drawn smaller."""
    for z in city.zones.values():
        assert z.radius_m >= city.constants["min_zone_radius_m"], z.id


# --------------------------------------------------------------------------
# The danger verdict
# --------------------------------------------------------------------------

ZONE = "zone_stadium_north_concourse"


def _ev(**kw):
    base = dict(zone_id=ZONE, people=8000.0, people_rate_per_min=0.0,
                inside_sampled=30, sustained_s=0.0)
    base.update(kw)
    return Evidence(**base)


def test_draining_crowd_never_fires():
    """A dense crowd that is moving is a busy street, not a disaster."""
    v = assess(city, _ev(people=12000.0, people_rate_per_min=-400.0))
    assert not v.dangerous, v.reason
    assert "draining" in v.reason


def test_small_crowd_never_fires():
    """Below 1,200 people nothing is dangerous however slowly it moves."""
    v = assess(city, _ev(people=900.0, people_rate_per_min=5000.0, sustained_s=600.0))
    assert not v.dangerous, v.reason


def test_filling_faster_than_the_link_can_pass_fires():
    """More arriving than can leave, sustained, is the earliest true alarm."""
    capacity = city.zone_capacity_per_min(ZONE)
    v = assess(city, _ev(people=9000.0,
                         people_rate_per_min=capacity * 0.9,
                         sustained_s=180.0))
    assert v.dangerous, v.reason
    assert v.fired_by == "filling", v.fired_by
    assert v.hazard_segment_id == "seg_concourse_ramp"


def test_a_gentle_fill_does_not_fire():
    """
    A merely positive rate is not evidence. This is the case that produced a
    false alarm on a safe staggered release when the threshold was 20%.
    """
    capacity = city.zone_capacity_per_min(ZONE)
    v = assess(city, _ev(people=9000.0,
                         people_rate_per_min=capacity * 0.3,
                         sustained_s=600.0))
    assert not v.dangerous, v.reason


def test_not_clearing_fires_even_without_a_rate():
    """People who went in and did not come out is later, but certain."""
    v = assess(city, _ev(people=9000.0, people_rate_per_min=0.0, outflow_ratio=0.1))
    assert v.dangerous, v.reason
    assert v.fired_by == "not_clearing", v.fired_by


def test_too_few_devices_publishes_nothing():
    """Fewer than 5 devices inside is no answer, not a weak answer."""
    v = assess(city, _ev(people=20000.0, people_rate_per_min=5000.0,
                         inside_sampled=3, sustained_s=600.0))
    assert not v.dangerous
    assert "below the minimum" in v.reason


def test_headcount_is_published_as_a_band():
    """A single figure would claim a precision the sample does not have."""
    v = assess(city, _ev(people=10000.0))
    assert v.people_low < 10000 < v.people_high
    assert round(v.people_low) == 7000 and round(v.people_high) == 14000


# --------------------------------------------------------------------------
# Spending
# --------------------------------------------------------------------------

def test_the_soonest_crisis_is_funded_first():
    """
    Urgency beats size. For a large crowd twenty minutes away there is still
    time to come back; for a small one three minutes away there is not.
    """
    soon = Request("district_stadium", "zone_a", 100, severity=0.6,
                   people=3000, seconds_to_critical=180)
    later = Request("district_central", "zone_b", 100, severity=0.6,
                    people=15000, seconds_to_critical=1200)
    assert soon.priority() > later.priority()


def test_a_thin_budget_funds_one_properly_rather_than_three_badly():
    """Three samples too small to conclude from are worth less than one that is not."""
    b = Budget(per_hour=120, reserve_fraction=0.0)
    grants = b.allocate([
        Request("d1", "z1", 100, severity=0.9, people=9000, seconds_to_critical=120),
        Request("d2", "z2", 100, severity=0.5, people=4000, seconds_to_critical=900),
        Request("d3", "z3", 100, severity=0.4, people=2000, seconds_to_critical=None),
    ], now=0.0)
    funded = [z for z, n in grants.items() if n > 0]
    assert funded == ["z1"], grants
    assert grants["z1"] == 100


def test_retrieval_is_counted_as_the_expensive_call():
    """The ledger has to reflect that coordinates cost about 3x a verification."""
    from app.core.budget import TIER_RETRIEVE, TIER_VERIFY, TIER_WEIGHT
    assert TIER_WEIGHT[TIER_RETRIEVE] == 3.0 * TIER_WEIGHT[TIER_VERIFY]


# --------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------

def test_the_panel_estimate_is_a_simple_proportion():
    """15 of 45 panel members inside means about a third of the city is inside."""
    r = DeviceRegistry()
    assert r.people_from_panel(15, 45, 30000) == 10000.0
    # No sample means no answer, not zero people.
    assert r.people_from_panel(0, 0, 30000) == 0.0


def test_a_phone_number_never_leaves_the_vault():
    """Everything outside the vault refers to a device by hash only."""
    r = DeviceRegistry()
    h = r.add_panel("+97430001234")
    assert "+974" not in h
    assert r.vault.phone_for(h) == "+97430001234"

    # Enrolling places nobody. This used to assert the opposite, because a
    # district passed at enrolment was written straight into the registry as
    # though it had been measured. Only a geofence notification may place a
    # device now; see tests/test_placement.py.
    assert r.district_of(h) is None
    r.place(h, "district_stadium", 0.0)
    assert r.district_of(h) == "district_stadium"


# --------------------------------------------------------------------------

def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  pass  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
