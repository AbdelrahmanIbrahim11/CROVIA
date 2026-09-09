"""
The CAMARA layer, and the two things Nokia told us that shape it.

  "Simulated devices do not move."
      In the sandbox no device ever crosses a geofence boundary, so
      area-entered and area-left never fire. Any design that depends on those
      events produces nothing at all in the sandbox. Counting with Location
      Verification works either way, so counting is the primary sensor and
      geofence events are a bonus.

  "You can use different phone numbers to get different response."
      Each test number has a fixed answer. A crowd can still be demonstrated
      honestly by choosing WHICH numbers to ask about over time: ask numbers
      that answer "outside" early and numbers that answer "inside" later. Every
      call is real; only the choice of who to ask is scripted.

Two implementations behind one interface:

  NokiaClient      talks to the real Network as Code API
  SimulatorClient  answers locally from Nokia's documented test numbers, so the
                   whole pipeline runs with no network and no quota
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from app.core.budget import (
    TIER_CONGESTION_SUB, TIER_DELETE, TIER_GEOFENCE_SUB,
    TIER_REACHABILITY, TIER_RETRIEVE, TIER_VERIFY, Ledger,
)

# Nokia's documented simulator numbers.
SIM_VERIFY = {
    "+99999991000": "FALSE",    # not in the given area
    "+99999991001": "TRUE",     # in the given area
    "+99999991002": "PARTIAL",  # partially within
    "+99999991003": "UNKNOWN",  # location unknown
}
SIM_REACHABILITY = {
    "+99999991000": ["SMS"],
    "+99999991001": ["DATA"],
    "+99999991002": ["DATA", "SMS"],
    "+99999991003": [],         # lost connectivity
}
SIM_ERRORS = {
    "+99999990400": 400, "+99999990404": 404, "+99999990422": 422,
    "+99999990500": 500, "+99999990502": 502, "+99999990503": 503,
    "+99999990504": 504,
}


class ApiError(Exception):
    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(f"HTTP {status} {message}".strip())
        self.status = status


@dataclass
class Area:
    lat: float
    lon: float
    radius_m: float


class CamaraClient(Protocol):
    ledger: Ledger

    def verify_location(self, phone: str, area: Area) -> dict: ...
    def get_reachability(self, phone: str) -> dict: ...
    def retrieve_location(self, phone: str, max_age_s: int = 90) -> dict: ...
    def create_congestion_subscription(self, phone: str, sink: str, expire_s: int) -> str: ...
    def create_geofence_subscription(self, phone: str, area_id: str, area: Area,
                                     sink: str, expire_s: int,
                                     initial_event: bool = True) -> tuple[str, dict | None]: ...
    def delete_subscription(self, sub_id: str) -> None: ...


class SimulatorClient:
    """
    Answers from Nokia's published test numbers. No network, no quota.

    This is not a fake: the responses are exactly what the sandbox returns for
    those numbers, including the error codes. What it cannot do is move a
    device, because the sandbox cannot either.
    """

    def __init__(self, ledger: Ledger | None = None) -> None:
        self.ledger = ledger or Ledger()
        self._seq = 0
        self.subs: dict[str, dict] = {}

    def _meter(self, tier: str, phone: str, district: str | None = None) -> None:
        self.ledger.record(tier, district)
        if phone in SIM_ERRORS:
            status = SIM_ERRORS[phone]
            self.ledger.record_error(status)
            raise ApiError(status, "simulator error number")

    def verify_location(self, phone: str, area: Area, district: str | None = None) -> dict:
        self._meter(TIER_VERIFY, phone, district)
        result = SIM_VERIFY.get(phone, "UNKNOWN")
        out = {"verification_result": result}
        if result == "PARTIAL":
            out["match_rate"] = 60
        return out

    def get_reachability(self, phone: str, district: str | None = None) -> dict:
        self._meter(TIER_REACHABILITY, phone, district)
        conn = SIM_REACHABILITY.get(phone, [])
        return {"reachable": bool(conn), "connectivity": conn}

    def retrieve_location(self, phone: str, max_age_s: int = 90,
                          district: str | None = None) -> dict:
        self._meter(TIER_RETRIEVE, phone, district)
        if SIM_VERIFY.get(phone) == "UNKNOWN":
            return {"status": "UNKNOWN"}
        return {"status": "OK", "latitude": 25.424, "longitude": 51.4904, "radius_m": 400.0}

    def create_congestion_subscription(self, phone: str, sink: str, expire_s: int) -> str:
        self._meter(TIER_CONGESTION_SUB, phone)
        self._seq += 1
        sid = f"sim-cong-{self._seq}"
        self.subs[sid] = {"kind": "congestion", "phone": phone}
        return sid

    def create_geofence_subscription(self, phone: str, area_id: str, area: Area,
                                     sink: str, expire_s: int,
                                     initial_event: bool = True) -> tuple[str, dict | None]:
        self._meter(TIER_GEOFENCE_SUB, phone)
        self._seq += 1
        sid = f"sim-geo-{self._seq}"
        self.subs[sid] = {"kind": "geofence", "phone": phone, "area": area_id}
        evt = None
        if initial_event:
            inside = SIM_VERIFY.get(phone) == "TRUE"
            evt = {"type": "area-entered" if inside else "area-left",
                   "subscriptionId": sid, "areaId": area_id}
        return sid, evt

    def delete_subscription(self, sub_id: str) -> None:
        self.ledger.record(TIER_DELETE)
        self.subs.pop(sub_id, None)


class NokiaClient:
    """The real Network as Code API."""

    def __init__(self, api_key: str, ledger: Ledger | None = None,
                 host: str = "network-as-code.nokia.rapidapi.com") -> None:
        import network_as_code as nac
        self._nac = nac.NetworkAsCodeApi(rapidapi_host=host, api_key=api_key)
        self.ledger = ledger or Ledger()

    def verify_location(self, phone: str, area: Area, district: str | None = None) -> dict:
        self.ledger.record(TIER_VERIFY, district)
        r = self._nac.location.verify_v1(
            device={"phone_number": phone},
            area={"area_type": "CIRCLE",
                  "center": {"latitude": area.lat, "longitude": area.lon},
                  "radius": int(area.radius_m)},
            max_age=120,
        )
        out = {"verification_result": r.verification_result}
        if getattr(r, "match_rate", None) is not None:
            out["match_rate"] = r.match_rate
        return out

    def get_reachability(self, phone: str, district: str | None = None) -> dict:
        self.ledger.record(TIER_REACHABILITY, district)
        s = self._nac.device_status.retrieve_reachability_status(
            device={"phone_number": phone})
        return {"reachable": bool(getattr(s, "reachable", False)),
                "connectivity": list(getattr(s, "connectivity", []) or [])}

    def retrieve_location(self, phone: str, max_age_s: int = 90,
                          district: str | None = None) -> dict:
        self.ledger.record(TIER_RETRIEVE, district)
        loc = self._nac.location.retrieve(device={"phone_number": phone}, max_age=max_age_s)
        if loc is None or loc.latitude is None:
            return {"status": "UNKNOWN"}
        return {"status": "OK", "latitude": loc.latitude, "longitude": loc.longitude,
                "radius_m": float(getattr(loc, "radius", 400) or 400)}

    def create_congestion_subscription(self, phone: str, sink: str, expire_s: int) -> str:
        self.ledger.record(TIER_CONGESTION_SUB)
        sub = self._nac.congestion_insights.create_subscription(
            device={"phone_number": phone},
            webhook={"notification_url": sink},
            subscription_expire_time=dt.datetime.now(dt.timezone.utc)
            + dt.timedelta(seconds=expire_s),
        )
        return sub.subscription_id

    def create_geofence_subscription(self, phone: str, area_id: str, area: Area,
                                     sink: str, expire_s: int,
                                     initial_event: bool = True) -> tuple[str, dict | None]:
        self.ledger.record(TIER_GEOFENCE_SUB)
        sub = self._nac.geofencing.create_subscription(
            protocol="HTTP", sink=sink,
            types=["org.camaraproject.geofencing-subscriptions.v0.area-entered"],
            config={
                "subscription_detail": {
                    "device": {"phone_number": phone},
                    "area": {"area_type": "CIRCLE",
                             "center": {"latitude": area.lat, "longitude": area.lon},
                             "radius": int(area.radius_m)},
                },
                "subscription_expire_time": dt.datetime.now(dt.timezone.utc)
                + dt.timedelta(seconds=expire_s),
                "initial_event": initial_event,
            },
        )
        return sub.id, None

    def delete_subscription(self, sub_id: str) -> None:
        self.ledger.record(TIER_DELETE)
        try:
            self._nac.geofencing.delete_subscription(sub_id)
        except Exception:
            self._nac.congestion_insights.delete_subscription(resource_id=sub_id)
