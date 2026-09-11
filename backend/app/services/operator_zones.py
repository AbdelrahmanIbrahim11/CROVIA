"""
Zones an operator draws, rather than ones from the city plan.

A stadium or event manager knows things the city plan does not: which gate is
open tonight, where the temporary barriers went, which exit the away supporters
are being sent to. This lets them add a watch zone for it and have it judged by
exactly the same rules as every other zone - no separate code path, no weaker
verdict.

Two constraints are enforced here rather than left to the user interface,
because a rule that only exists in a screen is a rule that disappears the first
time someone calls the API directly.

MINIMUM RADIUS. Nothing below 600 m. Nokia's guidance is that geofence accuracy
is at cell-tower level and smaller circles give inconsistent results, and a
confident number drawn from an unreliable circle is worse than no number,
because someone may send staff to the wrong place because of it.

A LINK IS REQUIRED. The operator must give the width and length of the narrow
point. Everything the danger rule does starts there - capacity is width x 72,
and the area people are packed into is width x length. A circle with no link
cannot be judged at all, and guessing a width would produce a capacity figure
with nothing behind it.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.core.city import City
from app.detect.engine import ZoneState
from app.usersDB.models import operator_zone

logger = logging.getLogger("crovia.operator_zones")

_SLUG = re.compile(r"[^a-z0-9]+")


def zone_id_for(label: str) -> str:
    slug = _SLUG.sub("_", label.strip().lower()).strip("_") or "zone"
    return f"zone_op_{slug}"[:60]


def create(db: Session, city: City, engine, *, label: str, district_id: str,
           lat: float, lon: float, radius_m: float, width_m: float,
           length_m: float, risk: float = 1.3,
           created_by: str | None = None) -> dict:
    """
    Add a drawn zone to the running system and save it.

    The city model validates first, so an invalid zone never reaches the
    database and the two can never disagree about what exists.
    """
    label = (label or "").strip()
    if not label:
        raise ValueError("the place needs a name")
    # The column holds 120. Checked here so a long name is a readable refusal
    # rather than a 500 from the database, which is what a person typing a
    # description instead of a name would otherwise get.
    if len(label) > 120:
        raise ValueError("the name must be 120 characters or fewer")

    zone_id = zone_id_for(label)
    if zone_id in city.zones:
        raise ValueError(f"a zone called {label!r} already exists")

    zone = city.add_operator_zone(
        zone_id=zone_id, label=label, district_id=district_id,
        lat=lat, lon=lon, radius_m=radius_m,
        width_m=width_m, length_m=length_m, risk=risk,
    )

    # The engine keeps per-zone state. Without this the zone exists on the map
    # and is never counted, which looks like being watched and is not.
    engine.zones[zone_id] = ZoneState(zone_id, district_id)

    row = operator_zone(zone_id=zone_id, label=label, district_id=district_id,
                        lat=lat, lon=lon, radius_m=radius_m, width_m=width_m,
                        length_m=length_m, risk=risk, created_by=created_by)
    db.add(row)
    db.commit()

    capacity = city.zone_capacity_per_min(zone_id)
    logger.info("operator zone %s added: %.0f m link passes ~%.0f people/min",
                zone_id, width_m, capacity)
    return {
        "zone_id": zone_id, "label": zone.label, "district_id": district_id,
        "lat": lat, "lon": lon, "radius_m": radius_m,
        "width_m": width_m, "length_m": length_m,
        "capacity_per_min": round(capacity),
        "max_safe_people": round(width_m * length_m * city.density_critical),
    }


def remove(db: Session, city: City, engine, zone_id: str) -> bool:
    """Remove a drawn zone. Zones from the city plan cannot be deleted this way."""
    if not city.remove_operator_zone(zone_id):
        return False
    engine.zones.pop(zone_id, None)
    row = (db.query(operator_zone)
             .filter(operator_zone.zone_id == zone_id).one_or_none())
    if row is not None:
        row.active = False
        db.commit()
    logger.info("operator zone %s removed", zone_id)
    return True


def load_all(db: Session, city: City, engine) -> int:
    """
    Put the saved zones back after a restart.

    An operator should not have to redraw their gates every time the service
    restarts, least of all during the event that made them draw the gates.
    """
    rows = db.query(operator_zone).filter(operator_zone.active.is_(True)).all()
    loaded = 0
    for r in rows:
        if r.zone_id in city.zones:
            continue
        try:
            city.add_operator_zone(
                zone_id=r.zone_id, label=r.label, district_id=r.district_id,
                lat=r.lat, lon=r.lon, radius_m=r.radius_m,
                width_m=r.width_m, length_m=r.length_m, risk=r.risk,
            )
            engine.zones[r.zone_id] = ZoneState(r.zone_id, r.district_id)
            loaded += 1
        except ValueError as exc:
            # A saved zone that no longer validates - the geography file may
            # have changed under it. Skipped loudly rather than crashing
            # startup, because the rest of the city still needs watching.
            logger.warning("could not restore operator zone %s: %s", r.zone_id, exc)
    return loaded


def listing(db: Session) -> list[dict]:
    rows = (db.query(operator_zone)
              .filter(operator_zone.active.is_(True))
              .order_by(operator_zone.created_at.desc()).all())
    return [
        {"zone_id": r.zone_id, "label": r.label, "district_id": r.district_id,
         "lat": r.lat, "lon": r.lon, "radius_m": r.radius_m,
         "width_m": r.width_m, "length_m": r.length_m,
         "created_by": r.created_by,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]
