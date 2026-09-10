"""
Getting the warning to the people it is about.

Until now an alarm was published on the API and stopped there. A person only
learned about the danger if they happened to be looking at the app at the time,
which is the opposite of what a warning is for.

Three decisions shape this file.

WHO IS TOLD. Only devices the engine currently places in the affected district.
Warning the whole city about a stadium ramp is how people learn to swipe the
warning away, and the next one is swiped away too. The district is used rather
than the zone because that is the resolution the network actually gives us — a
device is known to be in the Stadium Precinct, not on the ramp.

WHAT IT SAYS. The place, the size, and one instruction. No distance and no
direction, because the network does not know where the person is standing to
that precision and a warning that guesses is worse than one that does not.

HOW OFTEN. One warning per person per incident. Re-confirmation of an alarm
already sent produces nothing, because a phone buzzing every minute during an
emergency is a phone that gets silenced.

The transport is deliberately pluggable and defaults to in-app delivery, which
is the only channel that is genuinely wired up. Nothing here pretends an SMS
was sent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.city import city
from app.usersDB.models import alert_delivery, monitored_device

logger = logging.getLogger("crovia.warnings")

# A transport takes (hashed_id, title, body) and raises on failure. The default
# records the warning for the app to collect. Registering a real SMS or push
# sender later does not require touching anything above this line.
Transport = Callable[[str, str, str], None]
_transports: dict[str, Transport] = {}


def register_transport(channel: str, fn: Transport) -> None:
    _transports[channel] = fn


def compose(record: dict) -> tuple[str, str]:
    """
    Turn a verdict into words a person can act on.

    Deliberately short. Someone reading this may be walking into the crowd it
    describes.
    """
    place = record.get("segment_label") or "A crossing ahead"
    low = record.get("people_low")
    high = record.get("people_high")
    width = record.get("width_m")
    capacity = record.get("capacity_per_min")

    title = f"Avoid {place}"
    size = (f"About {int(low):,}–{int(high):,} people are there. "
            if low is not None and high is not None else "")
    why = (f"The way out is {width:.0f} m wide and can pass about "
           f"{int(capacity):,} people a minute, and more are arriving than that. "
           if width and capacity else "")
    body = (f"{size}{why}Do not join this crowd. Wait where you are, or leave by "
            f"another route.")
    return title, body


def warn_people_near(db: Session, registry, record: dict,
                     incident_id=None, channel: str = "in_app") -> dict:
    """
    Send one warning to each monitored device in the affected district.

    Returns what happened, so the caller can log it and the operator screen can
    show how many people were actually reached.
    """
    zone_id = record.get("zone_id")
    zone = city.zones.get(zone_id)
    if zone is None:
        return {"sent": 0, "failed": 0, "already_warned": 0}

    recipients = registry.fleet(zone.district_id)
    if not recipients:
        logger.warning("alarm in %s but no devices are placed there - nobody to warn",
                       zone.district_id)
        return {"sent": 0, "failed": 0, "already_warned": 0}

    title, body = compose(record)
    transport = _transports.get(channel)

    # One per person per incident. Re-confirmation sends nothing.
    already = {
        h for (h,) in db.query(alert_delivery.hashed_id)
        .filter(alert_delivery.zone_id == zone_id,
                alert_delivery.incident_id == incident_id)
        .all()
    }

    sent = failed = 0
    for hashed in recipients:
        if hashed in already:
            continue
        row = alert_delivery(hashed_id=hashed, zone_id=zone_id,
                             incident_id=incident_id, channel=channel,
                             title=title, body=body)
        if transport is not None:
            try:
                transport(hashed, title, body)
            except Exception as exc:
                row.failed_reason = str(exc)[:200]
                failed += 1
        db.add(row)
        if row.failed_reason is None:
            sent += 1
    db.commit()

    logger.info("warned %d people in %s about %s (%d failed, %d already warned)",
                sent, zone.district_id, zone_id, failed, len(already))
    return {"sent": sent, "failed": failed, "already_warned": len(already),
            "district_id": zone.district_id}


def inbox(db: Session, hashed_id: str, limit: int = 20) -> list[dict]:
    """Warnings for one person, newest first."""
    rows = (db.query(alert_delivery)
              .filter(alert_delivery.hashed_id == hashed_id)
              .order_by(alert_delivery.sent_at.desc())
              .limit(limit).all())
    return [
        {"id": str(r.id), "zone_id": r.zone_id, "title": r.title, "body": r.body,
         "sent_at": r.sent_at.isoformat() if r.sent_at else None,
         "read": r.read_at is not None,
         "failed_reason": r.failed_reason}
        for r in rows
    ]


def mark_read(db: Session, delivery_id: str) -> bool:
    row = db.query(alert_delivery).filter(alert_delivery.id == delivery_id).one_or_none()
    if row is None:
        return False
    row.read_at = datetime.now(timezone.utc)
    db.commit()
    return True


def coverage(db: Session, zone_id: str, registry=None) -> dict:
    """
    How many people were reached, and how many could have been.

    An operator needs the second number to read the first one. "We warned 40
    people" means something very different when 4,000 were in the district.

    The denominator comes from the engine's registry rather than the database,
    because the registry is what the engine is actually watching right now.
    Counting database rows instead reported "200 warned, 0 monitored" whenever
    devices had been loaded into the engine without a row of their own, which
    is exactly the kind of number that gets read out to a room and believed.
    """
    total = db.query(alert_delivery).filter(alert_delivery.zone_id == zone_id).count()
    read = (db.query(alert_delivery)
              .filter(alert_delivery.zone_id == zone_id,
                      alert_delivery.read_at.isnot(None)).count())

    zone = city.zones.get(zone_id)
    in_district = None
    if registry is not None and zone is not None:
        in_district = len(registry.fleet(zone.district_id))
        monitored = len(registry.vault)
    else:
        monitored = db.query(monitored_device).filter(
            monitored_device.active.is_(True)).count()

    return {"zone_id": zone_id, "warned": total, "read": read,
            "in_district": in_district, "monitored_total": monitored}
