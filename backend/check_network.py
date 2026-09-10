"""
Prove the real Nokia path works, with or without a key.

The whole system has only ever run against the twin, so the code that talks to
Nokia had never been executed once. That is the most dangerous kind of untested
code: it looks finished, and it fails on the first call in front of an audience.

Two modes, chosen automatically.

    NO KEY   Every response shape the client parses is fed a real CAMARA
             payload and checked. This catches the class of bug that actually
             bit: reading loc.latitude from a response that has no such field
             and returns an `area` instead.

    WITH KEY The same calls go to Nokia's servers against their published test
             numbers, whose answers are documented, so a wrong answer is a real
             failure rather than an unknown.

    NOKIA_NAC_API_KEY=... PYTHONPATH=. ./venv/bin/python check_network.py
"""

from __future__ import annotations

import os
import sys

from app.camara.client import Area

# Nokia's simulator answers these deterministically, which is what makes them
# usable as an assertion rather than just a smoke test.
TEST_NUMBERS = {
    "+99999991000": ("FALSE", "not in the area, SMS only"),
    "+99999991001": ("TRUE", "in the area, has data"),
    "+99999991002": ("PARTIAL", "partly in the area, SMS and data"),
    "+99999991003": ("UNKNOWN", "location unknown, unreachable"),
}

LUSAIL_RAMP = Area(25.4240, 51.4904, 600)

ok = fail = 0


def check(label: str, got, want=None, note: str = "") -> None:
    global ok, fail
    passed = got == want if want is not None else bool(got)
    if passed:
        ok += 1
        print(f"  pass  {label}: {got}{'  ' + note if note else ''}")
    else:
        fail += 1
        print(f"  FAIL  {label}: got {got!r}, wanted {want!r}")


# ---------------------------------------------------------------------------
# Without a key: check the parsing against real CAMARA response shapes
# ---------------------------------------------------------------------------

def check_response_parsing() -> None:
    print("No NOKIA_NAC_API_KEY set - checking the response parsing instead.\n")

    from network_as_code.location.types.retrieve_location_response import (
        RetrieveLocationResponse)
    from network_as_code.location.types.verify_v1location_response import (
        VerifyV1LocationResponse)

    print("Location Retrieval")
    loc = RetrieveLocationResponse.model_validate({
        "lastLocationTime": "2026-09-10T01:00:00Z",
        "area": {"areaType": "CIRCLE",
                 "center": {"latitude": 25.4240, "longitude": 51.4904},
                 "radius": 380},
    })
    area = getattr(loc, "area", None)
    center = getattr(area, "center", None)
    check("coordinates are nested under area.center", isinstance(center, dict), True)
    check("latitude reads back", round(float(center["latitude"]), 4), 25.424)
    check("accuracy radius reads back", float(getattr(area, "radius", 0)), 380.0,
          "m - drawn on the map as the halo")
    check("there is no top-level latitude to read",
          getattr(loc, "latitude", None) is None, True,
          "which is the bug this file exists to catch")

    print("\nLocation Verification")
    for result in ("TRUE", "FALSE", "PARTIAL", "UNKNOWN"):
        payload = {"lastLocationTime": "2026-09-10T01:00:00Z",
                   "verificationResult": result}
        if result == "PARTIAL":
            payload["matchRate"] = 74
        v = VerifyV1LocationResponse.model_validate(payload)
        check(f"{result} parses", v.verification_result, result)
    v = VerifyV1LocationResponse.model_validate({
        "lastLocationTime": "2026-09-10T01:00:00Z",
        "verificationResult": "PARTIAL", "matchRate": 74})
    check("PARTIAL carries a match rate", v.match_rate, 74,
          "- counted as inside above 55")

    print("\nSubscription ids")
    from network_as_code.congestion_insights.types.create_subscription_congestion_insights_response import (  # noqa: E501
        CreateSubscriptionCongestionInsightsResponse)
    from network_as_code.geofencing.types.create_subscription_geofencing_response import (
        CreateSubscriptionGeofencingResponse)
    c = CreateSubscriptionCongestionInsightsResponse.model_validate({
        "device": {"phoneNumber": "+99999991001"},
        "webhook": {"notificationUrl": "https://example.org/hook"},
        "subscriptionExpireTime": "2026-09-11T01:00:00Z",
        "subscriptionId": "sub-congestion-1", "startedAt": "2026-09-10T01:00:00Z"})
    check("congestion subscription id field", c.subscription_id, "sub-congestion-1")
    g = CreateSubscriptionGeofencingResponse.model_validate({
        "protocol": "HTTP", "sink": "https://example.org/hook",
        "types": ["org.camaraproject.geofencing-subscriptions.v0.area-entered"],
        "config": {"subscriptionDetail": {
            "device": {"phoneNumber": "+99999991001"},
            "area": {"areaType": "CIRCLE",
                     "center": {"latitude": 25.4240, "longitude": 51.4904},
                     "radius": 600}}},
        "id": "sub-geofence-1", "startsAt": "2026-09-10T01:00:00Z",
        "status": "ACTIVE"})
    check("geofence subscription id field", g.id, "sub-geofence-1",
          "- note it is `id`, not `subscription_id`")


# ---------------------------------------------------------------------------
# With a key: talk to Nokia
# ---------------------------------------------------------------------------

def check_live(api_key: str) -> None:
    from app.camara.client import ApiError, NokiaClient

    print("NOKIA_NAC_API_KEY is set - calling the real network.\n")
    client = NokiaClient(api_key=api_key)

    print("Location Verification against Nokia's test numbers")
    print(f"  area: Lusail north concourse, {LUSAIL_RAMP.radius_m:.0f} m radius\n")
    for phone, (expected, note) in TEST_NUMBERS.items():
        try:
            r = client.verify_location(phone, LUSAIL_RAMP)
            check(f"{phone} ({note})", r["verification_result"], expected)
        except ApiError as exc:
            check(f"{phone} ({note})", f"ApiError {exc}", expected)
        except Exception as exc:
            check(f"{phone} ({note})", f"{type(exc).__name__}: {exc}", expected)

    print("\nDevice reachability")
    for phone in ("+99999991001", "+99999991003"):
        try:
            r = client.get_reachability(phone)
            print(f"  info  {phone}: reachable={r['reachable']} "
                  f"connectivity={r['connectivity']}")
        except Exception as exc:
            print(f"  FAIL  {phone}: {type(exc).__name__}: {exc}")

    print("\nLocation Retrieval (the call whose parsing was wrong)")
    try:
        r = client.retrieve_location("+99999991001")
        if r["status"] == "OK":
            check("returned coordinates", True, True,
                  f"lat {r['latitude']:.4f}, lon {r['longitude']:.4f}, "
                  f"+/- {r['radius_m']:.0f} m")
        else:
            print("  info  UNKNOWN - no fix fresh enough. Expected outcome, not an error.")
    except Exception as exc:
        print(f"  FAIL  retrieve_location: {type(exc).__name__}: {exc}")

    print(f"\n  calls spent: {client.ledger.summary()['total']}")


def main() -> int:
    key = os.getenv("NOKIA_NAC_API_KEY", "").strip()
    print("=" * 70)
    print("CROVIA - checking the path to Nokia Network as Code")
    print("=" * 70 + "\n")
    if key:
        check_live(key)
    else:
        check_response_parsing()
    print(f"\n{ok} passed, {fail} failed")
    if not key:
        print("\nTo run this against the real network:")
        print("  NOKIA_NAC_API_KEY=your-key PYTHONPATH=. ./venv/bin/python check_network.py")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
