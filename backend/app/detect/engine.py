"""
The orchestrator, and the part that only matters once the city has more than
one crowd at the same time.

With a single incident there is nothing to decide: spend what is needed. With
two, a fixed hourly budget has to be split, and splitting it evenly is the
wrong answer. Three half-funded answers are three samples too small to act on.
One funded answer plus two honestly marked "unresolved" is more useful.

So each tick does this:

  1. For every district, gather the evidence that costs nothing. Congestion
     arrives pushed; the panel count from the previous tick is already held.
  2. Rank the districts that look like they need attention.
  3. Ask the budget to split what is available, urgency first.
  4. Spend only where funding was granted, and record the rest as unresolved
     rather than pretending they were checked.

The state per district is independent, so two crowds never overwrite each
other's evidence.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.camara.client import Area, ApiError, CamaraClient
from app.core.budget import Budget, Ledger, Request
from app.core.city import City
from app.core.registry import DeviceRegistry
from app.detect.danger import Evidence, Verdict, assess

IDLE, WATCHING, CONFIRMING, ALERT, STANDDOWN = "IDLE", "WATCHING", "CONFIRMING", "ALERT", "STANDDOWN"


@dataclass
class ZoneState:
    zone_id: str
    district_id: str
    counts: deque = field(default_factory=lambda: deque(maxlen=30))  # (t, people)
    filling_since: float | None = None
    last_verdict: Verdict | None = None
    last_checked: float = 0.0
    unresolved_since: float | None = None

    def rate_per_min(self) -> float:
        """Change in the panel headcount, in real people per minute."""
        if len(self.counts) < 2:
            return 0.0
        (t0, p0), (t1, p1) = self.counts[0], self.counts[-1]
        span = t1 - t0
        if span < 120:
            return 0.0
        return (p1 - p0) / (span / 60.0)

    def span_s(self) -> float:
        if len(self.counts) < 2:
            return 0.0
        return self.counts[-1][0] - self.counts[0][0]


@dataclass
class DistrictState:
    district_id: str
    state: str = IDLE
    high_devices: dict = field(default_factory=dict)   # hashed -> last seen at
    armed_at: float | None = None


class Engine:
    def __init__(self, city: City, client: CamaraClient, registry: DeviceRegistry,
                 budget: Budget | None = None, panel_sample: int = 45) -> None:
        self.city = city
        self.client = client
        self.registry = registry
        self.budget = budget or Budget()
        self.panel_sample = panel_sample
        self.ledger: Ledger = client.ledger
        self.districts = {d: DistrictState(d) for d in city.districts}
        self.zones = {z.id: ZoneState(z.id, z.district_id) for z in city.zones.values()}
        self.trace: list[dict] = []
        self.alerts: list[dict] = []
        self.now = 0.0

    # ------------------------------------------------------------------

    def log(self, kind: str, msg: str, **extra) -> None:
        self.trace.append({"t": self.now, "kind": kind, "msg": msg, **extra})

    # ---- free evidence -------------------------------------------------

    def on_congestion(self, sub_id: str, level: str, confidence: int) -> None:
        """
        A congestion notification. It carries no location and no device id, so
        the district can only come from our own registry, which the district
        geofences keep up to date.
        """
        if level not in ("High", "Medium") or confidence < 50:
            return
        hashed = self.registry.sub_device.get(sub_id)
        if not hashed:
            return
        district = self.registry.district_of(hashed)
        if not district:
            return
        self.districts[district].high_devices[hashed] = self.now

    def on_geofence(self, sub_id: str, event_type: str) -> None:
        hashed = self.registry.sub_device.get(sub_id)
        area = self.registry.sub_area.get(sub_id)
        kind = self.registry.sub_kind.get(sub_id)
        if not hashed or not area:
            return
        if kind == "district":
            if event_type == "area-entered":
                self.registry.place(hashed, area, self.now)
            else:
                self.registry.remove_from(hashed, area)

    def _prune(self, window_s: float = 900.0) -> None:
        cut = self.now - window_s
        for st in self.districts.values():
            for h in [h for h, t in st.high_devices.items() if t < cut]:
                st.high_devices.pop(h, None)

    def _congestion_signal(self) -> dict[str, float]:
        """Share of each district's fleet reporting congestion."""
        out = {}
        for did, st in self.districts.items():
            fleet = max(len(self.registry.fleet(did)), 1)
            out[did] = len(st.high_devices) / fleet
        return out

    # ---- paid evidence -------------------------------------------------

    def count_zone(self, zone_id: str, max_calls: int) -> tuple[float, int, int]:
        """
        Count people inside a zone using Location Verification.

        This is the main sensor. It needs no subscription, returns no
        coordinates, and works even though sandbox devices never move — which
        is why it replaced counting geofence crossings.

        Returns (people, inside, checked).
        """
        z = self.city.zones[zone_id]
        area = Area(z.center.lat, z.center.lon, z.radius_m)
        panel = self.registry.panel_members()
        if not panel:
            return 0.0, 0, 0

        take = min(self.panel_sample, len(panel), max_calls)
        inside = checked = 0
        for hashed in panel[:take]:
            phone = self.registry.vault.phone_for(hashed)
            if not phone:
                continue
            try:
                r = self.client.verify_location(phone, area, z.district_id)
            except ApiError:
                continue
            self.budget.spend(1, self.now)
            checked += 1
            res = r["verification_result"]
            if res == "TRUE" or (res == "PARTIAL" and r.get("match_rate", 0) >= 55):
                inside += 1

        people = self.registry.people_from_panel(inside, checked, self.city.population)
        return people, inside, checked

    # ---- the tick ------------------------------------------------------

    def tick(self, now: float | None = None) -> list[Verdict]:
        self.now = time.time() if now is None else now
        self._prune()

        shares = self._congestion_signal()
        vals = sorted(shares.values())
        median = vals[len(vals) // 2] if vals else 0.0
        # Every district elevated together is a network fault, not a crowd.
        city_wide = sum(1 for v in shares.values() if v > 0.35) >= max(3, len(shares) - 1)

        # 1. Which zones deserve paid attention?
        wanted: list[Request] = []
        for zid, zs in self.zones.items():
            did = zs.district_id
            share = shares.get(did, 0.0)
            interesting = (
                (not city_wide and share >= 0.10 and share >= 2.0 * max(median, 0.01))
                or self.districts[did].state in (WATCHING, CONFIRMING, ALERT)
                or zs.rate_per_min() > 0
            )
            if not interesting:
                continue
            last = zs.last_verdict
            wanted.append(Request(
                district_id=did, zone_id=zid,
                calls_wanted=self.panel_sample,
                severity=last.severity if last else 0.4,
                people=last.people_low if last else 0.0,
                seconds_to_critical=last.seconds_to_critical if last else None,
            ))

        if city_wide:
            self.log("suppress", "every district is elevated together - that is a network "
                                 "event, not a crowd. Not spending.")
            return []
        if not wanted:
            return []

        # 2. Split the money, urgency first.
        grants = self.budget.allocate(wanted, self.now)
        if len(wanted) > 1:
            self.log("allocate",
                     f"{len(wanted)} zones want attention; budget split "
                     + ", ".join(f"{r.zone_id[5:]}={grants.get(r.district_id, 0)}" for r in wanted),
                     grants={r.zone_id: grants.get(r.district_id, 0) for r in wanted})

        # 3. Spend where funded.
        verdicts: list[Verdict] = []
        for req in wanted:
            zs = self.zones[req.zone_id]
            allowed = grants.get(req.district_id, 0)
            if allowed <= 0:
                zs.unresolved_since = zs.unresolved_since or self.now
                self.log("unresolved",
                         f"{req.zone_id[5:]}: no budget this cycle - marked unresolved, "
                         "not silently treated as safe", zone=req.zone_id)
                continue

            people, inside, checked = self.count_zone(req.zone_id, allowed)
            if checked == 0:
                continue
            zs.unresolved_since = None
            zs.counts.append((self.now, people))
            zs.last_checked = self.now

            rate = zs.rate_per_min()
            capacity = self.city.zone_capacity_per_min(req.zone_id)
            if rate >= 0.60 * capacity:
                zs.filling_since = zs.filling_since or self.now
            else:
                zs.filling_since = None
            sustained = 0.0 if zs.filling_since is None else self.now - zs.filling_since

            v = assess(self.city, Evidence(
                zone_id=req.zone_id, people=people, people_rate_per_min=rate,
                inside_sampled=inside, sustained_s=sustained,
            ))
            zs.last_verdict = v
            verdicts.append(v)

            ds = self.districts[req.district_id]
            if v.dangerous:
                if ds.state != ALERT:
                    ds.state = ALERT
                    self.alerts.append({"t": self.now, **v.to_dict()})
                    self.log("alert", f"{v.hazard_label}: {v.reason}", **v.to_dict())
            elif rate > 0:
                ds.state = WATCHING
            elif ds.state == ALERT:
                ds.state = STANDDOWN
                self.log("standdown", f"{req.zone_id[5:]} is clearing - releasing attention",
                         zone=req.zone_id)

        return verdicts

    def snapshot(self) -> dict:
        return {
            "t": self.now,
            "districts": {d: s.state for d, s in self.districts.items()},
            "zones": {z: (s.last_verdict.to_dict() if s.last_verdict else None)
                      for z, s in self.zones.items()},
            "unresolved": [z for z, s in self.zones.items() if s.unresolved_since],
            "spend": self.ledger.summary(),
            "alerts": len(self.alerts),
        }
