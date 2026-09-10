"""
Writing alarms down so they survive a restart.

Until now an alarm existed only in the engine's memory. That had two costs. A
restart during an incident erased the fact that it had ever happened, which is
exactly the moment the record matters most. And the `incidents` table was
written to hold history that baselines could later be built from, while nothing
ever put a row in it.

The engine still decides alarms entirely on its own. It calls in here through
an optional hook, so detection keeps working with no database at all — which is
what the simulation does, and what a database outage must not be allowed to
stop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.usersDB.models import incident

logger = logging.getLogger("crovia.incidents")


def open_incident(db: Session, record: dict) -> incident:
    """
    Record an alarm that has just been raised.

    Re-raising in a zone that is already open does not create a second row. One
    crowd is one incident even if the engine re-confirms it, because an operator
    reading the history needs to count events, not confirmations.
    """
    zone_id = record.get("zone_id")
    existing = (db.query(incident)
                  .filter(incident.zone_id == zone_id, incident.ended_at.is_(None))
                  .one_or_none())
    if existing is not None:
        return existing

    row = incident(
        zone_id=zone_id,
        segment_id=record.get("segment"),
        people_low=int(record["people_low"]) if record.get("people_low") is not None else None,
        people_high=int(record["people_high"]) if record.get("people_high") is not None else None,
        pinch_density=record.get("pinch_density"),
        fired_by=record.get("fired_by"),
        reason=record.get("reason"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("incident opened: %s (%s)", zone_id, record.get("fired_by"))
    return row


def close_incident(db: Session, zone_id: str) -> bool:
    """Mark the open incident in this zone as finished. Safe to call twice."""
    row = (db.query(incident)
             .filter(incident.zone_id == zone_id, incident.ended_at.is_(None))
             .one_or_none())
    if row is None:
        return False
    row.ended_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("incident closed: %s", zone_id)
    return True


def acknowledge(db: Session, incident_id: str, who: str) -> dict | None:
    """
    Record that a named person has seen this alarm and is dealing with it.

    Acknowledging does not close the incident. The crowd is still there. It
    changes one thing only: the alarm is no longer unanswered, and the operator
    screen can stop treating it as needing attention from someone else.

    Acknowledging twice keeps the first name and time. The question afterwards
    is who responded first, not who looked at it last.
    """
    row = db.query(incident).filter(incident.id == _as_uuid(incident_id)).one_or_none()
    if row is None:
        return None
    if row.acknowledged_at is None:
        row.acknowledged_at = datetime.now(timezone.utc)
        row.acknowledged_by = who
        db.commit()
        logger.info("incident %s acknowledged by %s", row.zone_id, who)
    return _as_dict(row)


def close_by_hand(db: Session, incident_id: str, who: str,
                  action_taken: str | None = None) -> dict | None:
    """
    Close an incident because a person dealt with it, and say what they did.

    Separate from the engine closing a zone when the count falls. The engine
    records that the crowd left; this records that somebody acted. Both are
    worth keeping, because "it cleared on its own" and "we opened two more
    gates" are different lessons for the next event.
    """
    row = db.query(incident).filter(incident.id == _as_uuid(incident_id)).one_or_none()
    if row is None:
        return None
    if row.ended_at is None:
        row.ended_at = datetime.now(timezone.utc)
    row.closed_by = who
    if action_taken:
        row.action_taken = action_taken
    db.commit()
    logger.info("incident %s closed by %s", row.zone_id, who)
    return _as_dict(row)


def _as_uuid(value):
    import uuid
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def history(db: Session, limit: int = 50) -> list[dict]:
    """Past alarms, newest first, for the operator screen and for baselines."""
    rows = (db.query(incident)
              .order_by(incident.started_at.desc())
              .limit(limit)
              .all())
    return [_as_dict(r) for r in rows]


def _as_dict(r: incident) -> dict:
    return {
        "id": str(r.id),
        "zone_id": r.zone_id,
        "segment_id": r.segment_id,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        "duration_s": (
            round((r.ended_at - r.started_at).total_seconds())
            if r.started_at and r.ended_at else None
        ),
        "open": r.ended_at is None,
        "acknowledged": r.acknowledged_at is not None,
        "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
        "acknowledged_by": r.acknowledged_by,
        "closed_by": r.closed_by,
        "action_taken": r.action_taken,
        "people_low": r.people_low,
        "people_high": r.people_high,
        "pinch_density": r.pinch_density,
        "fired_by": r.fired_by,
        "reason": r.reason,
    }
