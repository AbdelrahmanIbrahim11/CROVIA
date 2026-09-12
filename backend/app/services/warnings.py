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
from app.services import push
from app.usersDB.models import alert_delivery, device_consent, monitored_device

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

    # Who gets told, in two groups.
    #
    # The first is everyone the network has placed in the affected district.
    # That is the precise group and it is the one we want.
    in_district = list(registry.fleet(zone.district_id))

    # The second is everyone who has agreed to be monitored but whose district
    # is not known yet - somebody who signed up minutes ago and has not
    # produced a geofence event, so the network has not told us where they are.
    #
    # They are warned too. An unknown location is not evidence of safety, and
    # the message names the place to avoid rather than claiming the person is
    # near it. Staying silent would mean the people who most recently chose to
    # be protected are the ones protected least.
    unplaced = [h for h in _consented_hashes(db)
                if registry.district_of(h) is None]

    recipients = list(dict.fromkeys(in_district + unplaced))
    if not recipients:
        logger.warning("alarm in %s but nobody is enrolled - nobody to warn",
                       zone.district_id)
        return {"sent": 0, "failed": 0, "already_warned": 0,
                "district_id": zone.district_id}

    title, body = compose(record)
    transport = _transports.get(channel)

    # One per person per incident. Re-confirmation sends nothing.
    already = {
        h for (h,) in db.query(alert_delivery.hashed_id)
        .filter(alert_delivery.zone_id == zone_id,
                alert_delivery.incident_id == incident_id,
                alert_delivery.kind == "warning")
        .all()
    }

    # Look up where these people can be reached on a phone, once, before the
    # loop. One query rather than one per person.
    phone_tokens = push.tokens_for(db, recipients)

    sent = failed = 0
    for hashed in recipients:
        if hashed in already:
            continue
        row = alert_delivery(hashed_id=hashed, zone_id=zone_id,
                             incident_id=incident_id, channel=channel,
                             kind="warning", title=title, body=body)
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

    # Now make the phones buzz.
    #
    # Done after the rows are committed, on purpose. The database is the record
    # that a person was warned; the notification is only the delivery. If the
    # push service is slow or down, the warning still exists and still appears
    # in the app, which is the part that must never depend on a third party.
    to_push: list[str] = []
    for hashed in recipients:
        if hashed in already:
            continue
        to_push.extend(phone_tokens.get(hashed, []))

    pushed = {"accepted": 0, "failed": 0}
    if to_push:
        pushed = push.send(db, to_push, title, body,
                           data={"zone_id": zone_id, "kind": "crowd_warning"})

    logger.info("warned %d people in %s about %s (%d failed, %d already warned, "
                "%d phones reached)",
                sent, zone.district_id, zone_id, failed, len(already),
                pushed["accepted"])
    return {"sent": sent, "failed": failed, "already_warned": len(already),
            "district_id": zone.district_id,
            "in_district": len(in_district), "location_unknown": len(unplaced),
            # How many were reached on a phone, against how many were told at
            # all. A person with no app installed is warned in the app only.
            "pushed": pushed["accepted"], "push_failed": pushed["failed"],
            "no_phone_registered": sent - len(to_push) if sent >= len(to_push) else 0}


def all_clear(db: Session, incident_id, zone_id: str,
              channel: str = "in_app", because: dict | None = None) -> dict:
    """
    Tell the people who were warned that the crowd has gone.

    Sent to exactly the people who received the warning for this incident, and
    to nobody else. Somebody who was never told to avoid the place does not
    need to be told it is fine.

    This exists because the warning had no end. It said "avoid this place" and
    then sat in the app unchanged for ever, so a person opening the app an hour
    later read a live-looking warning about a ramp that had been empty for
    fifty minutes. A safety message nobody can tell the age of is a safety
    message people learn to ignore.
    """
    told = [h for (h,) in db.query(alert_delivery.hashed_id)
            .filter(alert_delivery.incident_id == incident_id,
                    alert_delivery.kind == "warning").distinct().all()]
    if not told:
        return {"sent": 0}

    # Nobody is told twice, in case an incident is closed more than once.
    done = {h for (h,) in db.query(alert_delivery.hashed_id)
            .filter(alert_delivery.incident_id == incident_id,
                    alert_delivery.kind == "all_clear").all()}
    recipients = [h for h in told if h not in done]
    if not recipients:
        return {"sent": 0, "already_told": len(done)}

    zone = city.zones.get(zone_id)
    place = zone.label if zone is not None else "the area"
    title = f"{place} is clear"
    # Say WHY, with the same numbers that raised the alarm.
    #
    # "It is fine now" asks for trust. "About 4,000 people left and the number
    # is falling by 900 a minute" gives a reason, and a person who was warned
    # deserves to know whether the danger passed or the system stopped looking.
    if because:
        n = because.get("people") or 0
        falling = because.get("falling_by") or 0
        width = because.get("width_m") or 0
        cap = because.get("capacity_per_min") or 0
        left = (f"About {n:,} people are still in the area, but the number is "
                f"falling by roughly {falling:,} a minute. "
                if n and falling else "")
        link = (f"The {width:.0f} m way out is now passing people faster than "
                f"they arrive, up to about {cap:,} a minute. "
                if width and cap else "")
        body = (f"{left}{link}The crowd is dispersing on its own, so the "
                f"earlier warning no longer applies.")
    else:
        body = ("The crowd there has dispersed and the route is moving normally "
                "again. The earlier warning no longer applies.")

    transport = _transports.get(channel)
    tokens = push.tokens_for(db, recipients)

    sent = 0
    for hashed in recipients:
        row = alert_delivery(hashed_id=hashed, zone_id=zone_id,
                             incident_id=incident_id, channel=channel,
                             kind="all_clear", title=title, body=body)
        if transport is not None:
            try:
                transport(hashed, title, body)
            except Exception as exc:
                row.failed_reason = str(exc)[:200]
        db.add(row)
        if row.failed_reason is None:
            sent += 1
    db.commit()

    to_push: list[str] = []
    for hashed in recipients:
        to_push.extend(tokens.get(hashed, []))
    pushed = {"accepted": 0}
    if to_push:
        pushed = push.send(db, to_push, title, body,
                           data={"zone_id": zone_id, "kind": "all_clear"})

    logger.info("all-clear for %s sent to %d people (%d phones reached)",
                zone_id, sent, pushed.get("accepted", 0))
    return {"sent": sent, "pushed": pushed.get("accepted", 0)}


def _consented_hashes(db: Session) -> list[str]:
    """Everyone who has agreed to be monitored and has not taken it back."""
    rows = (db.query(device_consent.hashed_id)
              .filter(device_consent.revoked_at.is_(None)).all())
    return [r[0] for r in rows]


def inbox(db: Session, hashed_id: str, limit: int = 20) -> list[dict]:
    """
    Warnings for one person, newest first, each saying whether it still applies.

    `active` is the field that matters. A warning used to be returned exactly
    the same whether the crowd was still building or had dispersed an hour ago,
    so the app had no way to show the difference and a stale warning looked
    identical to a live one.

    The answer is already in the database - an incident records `ended_at` the
    moment the alert clears - it was simply never read back to the person who
    was warned.
    """
    from app.usersDB.models import incident

    rows = (db.query(alert_delivery, incident)
              .outerjoin(incident, alert_delivery.incident_id == incident.id)
              .filter(alert_delivery.hashed_id == hashed_id)
              .order_by(alert_delivery.sent_at.desc())
              .limit(limit).all())

    now = datetime.now(timezone.utc)
    out = []
    for r, inc in rows:
        ended = inc.ended_at if inc is not None else None
        sent = r.sent_at
        age_s = None
        if sent is not None:
            # Rows written before timezone support can come back naive.
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            age_s = max(0, int((now - sent).total_seconds()))
        out.append({
            "id": str(r.id), "zone_id": r.zone_id,
            "kind": r.kind or "warning",
            "title": r.title, "body": r.body,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "age_seconds": age_s,
            # False once the incident it belongs to has closed. An all-clear is
            # never "active" - it is the notice that something ended.
            "active": (r.kind or "warning") == "warning" and ended is None,
            "ended_at": ended.isoformat() if ended else None,
            "read": r.read_at is not None,
            "failed_reason": r.failed_reason,
        })
    return out


def mark_read(db: Session, delivery_id: str, owner_hash: str | None = None) -> bool:
    """
    Mark one warning as seen.

    When owner_hash is given the row must belong to that person, and a warning
    belonging to somebody else is reported as not found rather than as
    forbidden - confirming that an id exists is itself a leak.
    """
    q = db.query(alert_delivery).filter(alert_delivery.id == delivery_id)
    if owner_hash is not None:
        q = q.filter(alert_delivery.hashed_id == owner_hash)
    row = q.one_or_none()
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
