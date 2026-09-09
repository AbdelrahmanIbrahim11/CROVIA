"""
The city model: districts, zones, the walkable links inside them, and the
capacity maths that turns a street width into people per minute.

Everything is read from the shared geography file that the Expo app and the
simulation also read, so the three can never disagree about where a zone is or
how wide a ramp is.

The single most useful idea in this module:

    a link of width W can pass about  W * 72  people per minute

Peak pedestrian flow is roughly 1.2 people per metre of width per second, and
1.2 * 60 = 72. This needs no measurement and no API call — the number comes
from the city plan. It is what lets the system say "arrivals exceed what this
place can clear" while the crowd is still arriving.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

GEO_PATH = Path(__file__).resolve().parents[3] / "crovia-ui" / "src" / "geo" / "lusail.geo.json"

_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON_EQ = 111_320.0


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float

    def meters_to(self, other: "LatLon") -> float:
        dy = (other.lat - self.lat) * _M_PER_DEG_LAT
        dx = (other.lon - self.lon) * _M_PER_DEG_LON_EQ * math.cos(math.radians(self.lat))
        return math.hypot(dx, dy)


@dataclass(frozen=True)
class District:
    id: str
    label: str
    short: str
    center: LatLon
    radius_m: float
    notes: str = ""


@dataclass(frozen=True)
class Zone:
    id: str
    district_id: str
    label: str
    kind: str
    center: LatLon
    radius_m: float
    notes: str = ""


@dataclass(frozen=True)
class Segment:
    """
    A walkable link. Width decides throughput; length decides how many fit.

    The network cannot resolve a 9 m ramp — positioning error is far larger than
    the ramp itself. But we do not need to measure it: the plan already says
    where it is and how wide. Measurement locates the crowd to the corridor;
    the plan says which link inside that corridor will fail.
    """

    id: str
    zone_id: str
    label: str
    points: tuple[LatLon, ...]
    width_m: float
    risk: float
    drains_to: str | None

    @cached_property
    def length_m(self) -> float:
        return sum(self.points[i].meters_to(self.points[i + 1])
                   for i in range(len(self.points) - 1))

    @cached_property
    def area_m2(self) -> float:
        return self.length_m * self.width_m

    def capacity_per_min(self, per_m_per_min: float = 72.0) -> float:
        return self.width_m * per_m_per_min

    def max_safe_people(self, critical_density: float = 4.0) -> float:
        """Above this, the link is at the density where crowd disasters begin."""
        return self.area_m2 * critical_density


class City:
    def __init__(self, path: Path = GEO_PATH) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.raw = raw
        self.constants: dict = raw["constants"]
        self.meta: dict = raw["city"]

        self.districts: dict[str, District] = {
            d["id"]: District(
                id=d["id"], label=d["label"], short=d["short"],
                center=LatLon(d["center"]["lat"], d["center"]["lon"]),
                radius_m=float(d["radius_m"]), notes=d.get("notes", ""),
            )
            for d in raw["districts"]
        }

        self.zones: dict[str, Zone] = {
            z["id"]: Zone(
                id=z["id"], district_id=z["district_id"], label=z["label"],
                kind=z["kind"], center=LatLon(z["center"]["lat"], z["center"]["lon"]),
                radius_m=float(z["radius_m"]), notes=z.get("notes", ""),
            )
            for z in raw["zones"]
        }

        self.segments: dict[str, Segment] = {}
        for zone_id, segs in raw["segments"].items():
            z = self.zones[zone_id]
            m_lat = _M_PER_DEG_LAT
            m_lon = _M_PER_DEG_LON_EQ * math.cos(math.radians(z.center.lat))
            for s in segs:
                pts = tuple(
                    LatLon(z.center.lat + dy / m_lat, z.center.lon + dx / m_lon)
                    for dx, dy in s["offsets"]
                )
                self.segments[s["id"]] = Segment(
                    id=s["id"], zone_id=zone_id, label=s["label"], points=pts,
                    width_m=float(s["width_m"]), risk=float(s["risk"]),
                    drains_to=s.get("drains_to"),
                )

    # ---- constants -------------------------------------------------------

    @property
    def capacity_per_m(self) -> float:
        return float(self.constants["capacity_per_m_width_per_min"])

    @property
    def density_critical(self) -> float:
        return float(self.constants["density_critical_p_per_m2"])

    @property
    def min_zone_radius_m(self) -> float:
        return float(self.constants["min_zone_radius_m"])

    @property
    def population(self) -> int:
        return int(self.meta.get("population", 0))

    @property
    def app_users(self) -> int:
        return int(self.meta.get("app_users", 0))

    @property
    def penetration(self) -> float:
        """Share of people who have the app. Known from our own user database."""
        return self.app_users / max(self.population, 1)

    # ---- lookups ---------------------------------------------------------

    def zones_of(self, district_id: str) -> list[Zone]:
        return [z for z in self.zones.values() if z.district_id == district_id]

    def segments_of(self, zone_id: str) -> list[Segment]:
        return [s for s in self.segments.values() if s.zone_id == zone_id]

    def bottleneck_of(self, zone_id: str) -> Segment | None:
        """The narrowest link — the one that fails first."""
        segs = self.segments_of(zone_id)
        return min(segs, key=lambda s: s.width_m) if segs else None

    def zone_capacity_per_min(self, zone_id: str) -> float:
        b = self.bottleneck_of(zone_id)
        return b.capacity_per_min(self.capacity_per_m) if b else float("inf")

    def corridor_area_m2(self, zone_id: str) -> float:
        return sum(s.area_m2 for s in self.segments_of(zone_id)) or 1000.0

    def free_crossing_time_s(self, zone_id: str) -> float:
        """Roughly how long it takes to walk across the zone at free speed."""
        z = self.zones[zone_id]
        return (2.0 * z.radius_m) / float(self.constants["free_walk_speed_m_per_s"])

    def validate_radius(self, radius_m: float) -> None:
        """
        Refuse a circle the network cannot resolve.

        Showing confident numbers from an unreliable circle is worse than
        showing nothing, because a person may send staff to the wrong place.
        """
        if radius_m < self.min_zone_radius_m:
            raise ValueError(
                f"{radius_m:.0f} m is below the {self.min_zone_radius_m:.0f} m minimum. "
                "Geofence accuracy is at cell-tower level; smaller circles give "
                "inconsistent results."
            )


city = City()
