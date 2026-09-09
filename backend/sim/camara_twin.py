"""
A CAMARA client whose answers come from the twin, with the network's real
limitations put back in.

The engine under test cannot tell this apart from the live API. It sees the
same method names, the same response shapes, the same UNKNOWNs and the same
rate limits — but behind it the devices are actually moving, which the Nokia
sandbox cannot do.

The limitations reproduced on purpose:

  * positioning carries BOTH random error and a per-cell systematic bias. The
    bias matters: averaging many fixes removes the random half and leaves the
    systematic half untouched, which is why more samples alone never resolve a
    9 m ramp.
  * verification is judged against the uncertainty disc, so a device near the
    edge returns PARTIAL rather than a confident yes or no.
  * an unreachable device cannot be located at all.
  * congestion carries no location and no device id, only a subscription id.
"""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np

from app.camara.client import Area, ApiError
from app.core.budget import (
    TIER_CONGESTION_SUB, TIER_DELETE, TIER_GEOFENCE_SUB,
    TIER_REACHABILITY, TIER_RETRIEVE, TIER_VERIFY, Ledger,
)


class TwinCamaraClient:
    def __init__(self, twin, seed: int = 11, sigma_dense: float = 95.0,
                 sigma_sparse: float = 420.0, bias_scale: float = 90.0,
                 unknown_prob: float = 0.07, rate_limit_per_min: dict | None = None,
                 transient_error_prob: float = 0.015) -> None:
        self.twin = twin
        self.city = twin.city
        self.rng = np.random.default_rng(seed)
        self.ledger = Ledger()
        self.unknown_prob = unknown_prob
        self.transient_error_prob = transient_error_prob
        self.rate_limit = rate_limit_per_min or {TIER_RETRIEVE: 120, TIER_VERIFY: 300}
        self._windows: dict[str, deque] = defaultdict(deque)
        self.now = 0.0
        self._seq = 0
        self.subs: dict[str, dict] = {}
        self.phone_to_index: dict[str, int] = {}
        self._build_cells(sigma_dense, sigma_sparse, bias_scale)

    # ---- cells ----------------------------------------------------------

    def _build_cells(self, s_dense, s_sparse, bias_scale) -> None:
        c = self.city.meta["center"]
        pts = []
        for d in self.city.districts.values():
            dx = (d.center.lon - c["lon"]) * 111_320 * np.cos(np.radians(c["lat"]))
            dy = (d.center.lat - c["lat"]) * 110_540
            for _ in range(10 if d.radius_m <= 1000 else 7):
                th = self.rng.uniform(0, 2 * np.pi)
                r = d.radius_m * np.sqrt(self.rng.uniform(0, 1))
                pts.append((dx + r * np.cos(th), dy + r * np.sin(th)))
        self.cells = np.array(pts)
        n = len(pts)
        ang = self.rng.uniform(0, 2 * np.pi, n)
        mag = np.clip(self.rng.normal(bias_scale, bias_scale * 0.35, n), 10, None)
        self.bias = np.stack([mag * np.cos(ang), mag * np.sin(ang)], 1)
        d2 = ((self.cells[:, None, :] - self.cells[None, :, :]) ** 2).sum(-1)
        near = np.sort(d2, 1)[:, 1:4].mean(1) ** 0.5
        self.sigma = s_dense + np.clip((near - 250) / 900.0, 0, 1) * (s_sparse - s_dense)

    def _cell_of(self, i: int) -> int:
        d2 = (self.twin.x[i] - self.cells[:, 0]) ** 2 + (self.twin.y[i] - self.cells[:, 1]) ** 2
        return int(np.argmin(d2))

    # ---- plumbing -------------------------------------------------------

    def bind(self, phone: str, index: int) -> None:
        self.phone_to_index[phone] = index

    def _meter(self, tier: str, district: str | None = None) -> None:
        lim = self.rate_limit.get(tier)
        if lim is not None:
            w = self._windows[tier]
            while w and self.now - w[0] > 60:
                w.popleft()
            if len(w) >= lim:
                self.ledger.record_error(429)
                raise ApiError(429, "rate limited")
            w.append(self.now)
        self.ledger.record(tier, district)
        if self.rng.random() < self.transient_error_prob:
            st = int(self.rng.choice([500, 502, 503, 504]))
            self.ledger.record_error(st)
            raise ApiError(st, "transient")

    def _zone_xy(self, area: Area) -> tuple[float, float]:
        c = self.city.meta["center"]
        return ((area.lon - c["lon"]) * 111_320 * np.cos(np.radians(c["lat"])),
                (area.lat - c["lat"]) * 110_540)

    # ---- the API --------------------------------------------------------

    def verify_location(self, phone: str, area: Area, district: str | None = None) -> dict:
        self._meter(TIER_VERIFY, district)
        i = self.phone_to_index.get(phone)
        if i is None or not bool(self.twin.reachable[i]):
            return {"verification_result": "UNKNOWN"}
        ax, ay = self._zone_xy(area)
        d = float(np.hypot(self.twin.x[i] - ax, self.twin.y[i] - ay))
        sig = float(self.sigma[self._cell_of(i)])
        # Compare the uncertainty disc against the circle. Fully inside, fully
        # outside, or overlapping — which is what PARTIAL actually means.
        if d + sig <= area.radius_m:
            return {"verification_result": "TRUE"}
        if d - sig >= area.radius_m:
            return {"verification_result": "FALSE"}
        overlap = float(np.clip((area.radius_m - (d - sig)) / (2 * sig), 0.02, 0.98))
        return {"verification_result": "PARTIAL", "match_rate": int(overlap * 100)}

    def get_reachability(self, phone: str, district: str | None = None) -> dict:
        self._meter(TIER_REACHABILITY, district)
        i = self.phone_to_index.get(phone)
        ok = i is not None and bool(self.twin.reachable[i])
        return {"reachable": ok, "connectivity": ["DATA", "SMS"] if ok else []}

    def retrieve_location(self, phone: str, max_age_s: int = 90,
                          district: str | None = None) -> dict:
        self._meter(TIER_RETRIEVE, district)
        i = self.phone_to_index.get(phone)
        if i is None or not bool(self.twin.reachable[i]):
            return {"status": "UNKNOWN"}
        if self.rng.random() < self.unknown_prob:
            return {"status": "UNKNOWN"}
        cell = self._cell_of(i)
        sig = float(self.sigma[cell])
        b = self.bias[cell]
        x = self.twin.x[i] + b[0] + self.rng.normal(0, sig)
        y = self.twin.y[i] + b[1] + self.rng.normal(0, sig)
        c = self.city.meta["center"]
        lon = c["lon"] + x / (111_320 * np.cos(np.radians(c["lat"])))
        lat = c["lat"] + y / 110_540
        return {"status": "OK", "latitude": lat, "longitude": lon,
                "radius_m": float(np.clip(self.rng.normal(sig * 1.35, sig * 0.25), 60, 4000))}

    def create_congestion_subscription(self, phone: str, sink: str, expire_s: int) -> str:
        self._meter(TIER_CONGESTION_SUB)
        self._seq += 1
        sid = f"tw-cong-{self._seq}"
        self.subs[sid] = {"kind": "congestion", "phone": phone, "next": 0.0}
        return sid

    def create_geofence_subscription(self, phone: str, area_id: str, area: Area,
                                     sink: str, expire_s: int,
                                     initial_event: bool = True) -> tuple[str, dict | None]:
        self._meter(TIER_GEOFENCE_SUB)
        self._seq += 1
        sid = f"tw-geo-{self._seq}"
        i = self.phone_to_index.get(phone)
        inside = False
        if i is not None:
            ax, ay = self._zone_xy(area)
            inside = float(np.hypot(self.twin.x[i] - ax, self.twin.y[i] - ay)) <= area.radius_m
        self.subs[sid] = {"kind": "geofence", "phone": phone, "area": area_id, "inside": inside}
        evt = None
        if initial_event:
            evt = {"type": "area-entered" if inside else "area-left",
                   "subscriptionId": sid, "areaId": area_id}
        return sid, evt

    def delete_subscription(self, sub_id: str) -> None:
        self.ledger.record(TIER_DELETE)
        self.subs.pop(sub_id, None)

    # ---- pushed notifications ------------------------------------------

    def tick(self, now: float) -> list[dict]:
        """What a webhook would receive since the last tick."""
        self.now = now
        out: list[dict] = []
        loads = self._cell_loads()
        if self._baseline is None:
            self._baseline = np.maximum(loads.astype(float), 25.0)
        for sid, s in self.subs.items():
            if s["kind"] == "congestion":
                if now < s["next"]:
                    continue
                s["next"] = now + max(30.0, self.rng.normal(210, 60))
                i = self.phone_to_index.get(s["phone"])
                if i is None:
                    continue
                cell = self._cell_of(i)
                ratio = loads[cell] / max(self._baseline[cell], 25.0)
                level = ("High" if ratio > 2.2 else "Medium" if ratio > 1.6
                         else "Low" if ratio > 1.2 else "None")
                # No location and no device id, exactly like the real payload.
                out.append({"type": "congestion", "subscriptionId": sid,
                            "congestionLevel": level,
                            "confidenceLevel": int(np.clip(self.rng.normal(78, 12), 35, 99))})
            else:
                i = self.phone_to_index.get(s["phone"])
                if i is None:
                    continue
                z = self.city.districts.get(s["area"]) or self.city.zones.get(s["area"])
                if z is None:
                    continue
                ax, ay = self._zone_xy(Area(z.center.lat, z.center.lon, z.radius_m))
                now_in = float(np.hypot(self.twin.x[i] - ax, self.twin.y[i] - ay)) <= z.radius_m
                if now_in != s["inside"]:
                    s["inside"] = now_in
                    out.append({"type": "area-entered" if now_in else "area-left",
                                "subscriptionId": sid, "areaId": s["area"]})
        return out

    _baseline = None

    def _cell_loads(self) -> np.ndarray:
        d2 = ((self.twin.x[:, None] - self.cells[None, :, 0]) ** 2
              + (self.twin.y[:, None] - self.cells[None, :, 1]) ** 2)
        return np.bincount(np.argmin(d2, 1), minlength=len(self.cells))
