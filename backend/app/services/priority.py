"""
Giving responders a working connection during an incident.

The problem this solves is specific. A warning has to travel over the cell that
is congested, and that cell is congested *because* the crowd formed. The network
is at its worst at the exact moment it matters most - and the people who most
need it to work are the handful walking towards the crush, not the twelve
thousand posting video from inside it.

So when an alarm is raised, CROVIA asks the network to protect the connection
between each responder's phone and its own backend, and hands that priority back
when the incident closes.

Four decisions worth stating.

QOS_E, NOT QOS_L. The larger profiles chase throughput. QOS_E holds latency
steady under congestion with limited bandwidth, which is what a map, an incident
list and an acknowledge button need. A responder wants the app to answer, not to
download quickly.

RESPONDERS ONLY. A session is billed for as long as it lives, so prioritising
everyone in a district would mean hundreds of paid sessions per incident.
Prioritising the five people responding means five. It is also the only version
an operator would agree to: priority for emergency responders is defensible,
priority for an app's users is queue-jumping.

OPENED ON THE ALARM, NOT ON ACKNOWLEDGEMENT. Acknowledging is itself an action
taken in the app, so requiring it first would mean the connection is protected
only after it was already needed.

ALWAYS CLOSED. Sessions cost money while they live and the operator will
withdraw a priority that never ends. Every session is tied to an incident and
released when that incident closes, and any left behind by a restart are found
and closed from the database.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.usersDB.models import priority_session

logger = logging.getLogger("crovia.priority")

# Held in configuration rather than in the accounts table for now. Authority
# accounts have no phone number column yet, and the numbers of the people on
# duty tonight are an operational detail that changes shift by shift - not
# something a person types when they register.
def responder_devices() -> list[str]:
    raw = os.getenv("AUTHORITY_DEVICES", "")
    return [d.strip() for d in raw.split(",") if d.strip()]


def _server_ip() -> str:
    """
    The address QoD is asked to protect the route to.

    QoD prioritises traffic between a device and ONE named server, so this is
    CROVIA's own public address. Without it there is nothing to prioritise
    towards and the feature stays off.
    """
    return os.getenv("QOD_APP_SERVER_IP", "").strip()


def _profile() -> str:
    return os.getenv("QOD_PROFILE", "QOS_E").strip() or "QOS_E"


def _duration_s() -> int:
    # An hour by default. Long enough for an incident, short enough that a
    # session forgotten by a crash expires on its own rather than billing all
    # day. The maximum the API allows is 24 hours.
    return int(os.getenv("QOD_DURATION_SECONDS", "3600"))


def enabled() -> bool:
    return bool(responder_devices() and _server_ip())


def dispatch(db: Session, client, incident_id, zone_id: str) -> dict:
    """
    Open a priority session for every responder, for this incident.

    Never raises. A failure here must not stop an alarm: the warning has
    already been recorded and sent, and a responder without priority is still a
    responder who has been told.
    """
    if not enabled():
        return {"opened": 0, "skipped": "no responder devices or server address configured"}

    devices = responder_devices()
    server, profile, duration = _server_ip(), _profile(), _duration_s()

    # Someone already holding priority for this incident is not given a second
    # session. Sessions are billed individually.
    held = {
        d for (d,) in db.query(priority_session.device)
        .filter(priority_session.incident_id == incident_id,
                priority_session.closed_at.is_(None)).all()
    }

    sink = os.getenv("WEBHOOK_BASE_URL", "").strip()
    sink_url = f"{sink}/webhooks/qod" if sink and not sink.startswith("http://localhost") else None

    opened = failed = 0
    for device in devices:
        if device in held:
            continue
        row = priority_session(session_id=f"pending-{device}", incident_id=incident_id,
                               zone_id=zone_id, device=device, profile=profile)
        try:
            r = client.create_qod_session(device, server, profile, duration, sink_url)
            row.session_id = r["session_id"]
            row.status = r.get("status") or "REQUESTED"
            row.status_info = r.get("status_info")
            opened += 1
        except Exception as exc:
            row.status = "FAILED"
            row.error = f"{type(exc).__name__}: {exc}"[:200]
            row.closed_at = datetime.now(timezone.utc)
            failed += 1
        db.add(row)
    db.commit()

    logger.info("priority: %d responders given a protected connection for %s "
                "(%d failed)", opened, zone_id, failed)
    return {"opened": opened, "failed": failed, "profile": profile,
            "already_held": len(held)}


def stand_down(db: Session, client, incident_id) -> dict:
    """
    Hand the priority back when the incident is over.

    A session that fails to close is marked with the reason rather than being
    deleted from our side. Forgetting it here would leave it running and billed
    at the operator with nothing left that knows its id.
    """
    rows = (db.query(priority_session)
              .filter(priority_session.incident_id == incident_id,
                      priority_session.closed_at.is_(None)).all())
    closed = failed = 0
    for row in rows:
        try:
            client.delete_qod_session(row.session_id)
            row.closed_at = datetime.now(timezone.utc)
            row.status = "UNAVAILABLE"
            row.status_info = "DELETE_REQUESTED"
            closed += 1
        except Exception as exc:
            row.error = f"could not close: {type(exc).__name__}: {exc}"[:200]
            failed += 1
    db.commit()
    if closed or failed:
        logger.info("priority: released %d sessions (%d could not be closed)",
                    closed, failed)
    return {"closed": closed, "failed": failed}


def on_status_change(db: Session, session_id: str, status: str,
                     status_info: str | None) -> bool:
    """
    Record what the network decided.

    A session starts REQUESTED and only becomes AVAILABLE once resources are
    actually allocated - and the network can take it away again on its own with
    NETWORK_TERMINATED. A system that assumes priority is active because it
    asked for it will be wrong at some point, and this notification is the only
    way to find out.
    """
    row = (db.query(priority_session)
             .filter(priority_session.session_id == session_id).one_or_none())
    if row is None:
        return False
    row.status = status
    row.status_info = status_info
    if status == "UNAVAILABLE" and row.closed_at is None:
        row.closed_at = datetime.now(timezone.utc)
        if status_info == "NETWORK_TERMINATED":
            logger.warning("the network withdrew priority for %s during an incident",
                           row.device)
    db.commit()
    return True


def active(db: Session) -> list[dict]:
    """Who currently holds a protected connection, for the operator screen."""
    rows = (db.query(priority_session)
              .filter(priority_session.closed_at.is_(None))
              .order_by(priority_session.opened_at.desc()).all())
    return [{"session_id": r.session_id, "device": r.device, "zone_id": r.zone_id,
             "profile": r.profile, "status": r.status, "status_info": r.status_info,
             "opened_at": r.opened_at.isoformat() if r.opened_at else None,
             "error": r.error}
            for r in rows]


def close_orphans(db: Session, client) -> int:
    """
    Close sessions left open by a restart.

    Called at startup. Without it a crash during an incident leaves paid
    sessions running with nothing that remembers them.
    """
    rows = db.query(priority_session).filter(priority_session.closed_at.is_(None)).all()
    n = 0
    for row in rows:
        try:
            client.delete_qod_session(row.session_id)
        except Exception:
            pass
        row.closed_at = datetime.now(timezone.utc)
        row.status_info = "closed on restart"
        n += 1
    if n:
        db.commit()
        logger.info("released %d priority sessions left open by a restart", n)
    return n
