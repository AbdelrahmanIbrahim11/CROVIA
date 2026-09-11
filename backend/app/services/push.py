"""
Making a phone buzz.

A warning that only appears when the app is already open is not a warning. This
sends it to the phone itself, so it arrives on a locked screen.

Delivery goes through Expo's push service, which forwards to Apple and Google.
That is worth choosing deliberately: the alternative is talking to APNs and FCM
directly, which needs an Apple developer account, a Firebase project and two
sets of credentials, for the same result.

Three things this file is careful about.

IT NEVER PRETENDS. If a token is dead, the failure is recorded against that
person rather than swallowed, because "we warned 400 people" is a number that
gets read out in a room and believed.

IT IS NOT THE RECORD. The in-app list stays the record of what was sent. A push
can be silenced, blocked, or dropped by the network, so the database - not the
notification - is what proves a person was warned.

IT DOES NOT RUN ON THE WEB. A browser cannot produce a push token at all, so
there is nothing to send to and the whole path is skipped rather than failing.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.usersDB.models import push_token

logger = logging.getLogger("crovia.push")

EXPO_URL = "https://exp.host/--/api/v2/push/send"
# Expo accepts up to 100 messages per request. Batching matters during an
# incident: 400 separate calls would take longer than the warning is useful for.
BATCH = 100
TIMEOUT_S = 15


def register(db: Session, hashed_id: str, token: str,
             platform: str | None = None) -> push_token:
    """
    Remember where this device can be reached.

    The same token re-registering updates its row instead of adding one.
    Tokens are reissued when an app is reinstalled, and a person who
    accumulates dead addresses gets every alarm sent to all of them.
    """
    row = db.query(push_token).filter(push_token.token == token).one_or_none()
    if row is None:
        row = push_token(hashed_id=hashed_id, token=token, platform=platform)
        db.add(row)
    else:
        row.hashed_id = hashed_id
        row.platform = platform or row.platform
        row.invalid_reason = None
    row.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def unregister(db: Session, token: str) -> bool:
    """Forget a device. Called when a person signs out."""
    row = db.query(push_token).filter(push_token.token == token).one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def tokens_for(db: Session, hashed_ids: list[str]) -> dict[str, list[str]]:
    """Live addresses for these people, grouped by person."""
    if not hashed_ids:
        return {}
    rows = (db.query(push_token)
              .filter(push_token.hashed_id.in_(hashed_ids),
                      push_token.invalid_reason.is_(None))
              .all())
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r.hashed_id, []).append(r.token)
    return out


def send(db: Session, tokens: list[str], title: str, body: str,
         data: dict | None = None) -> dict:
    """
    Push one message to many devices.

    Returns how many were accepted and how many were refused. A refusal is
    recorded against the token so a dead address is not tried on every future
    alarm, and so coverage figures stay honest.
    """
    if not tokens:
        return {"accepted": 0, "failed": 0}

    accepted = failed = 0
    for i in range(0, len(tokens), BATCH):
        chunk = tokens[i:i + BATCH]
        messages = [{
            "to": t,
            "title": title,
            "body": body,
            # A crowd warning should arrive now, not when the phone next wakes.
            "priority": "high",
            "sound": "default",
            "data": data or {},
        } for t in chunk]

        try:
            req = urllib.request.Request(
                EXPO_URL,
                data=json.dumps(messages).encode(),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                payload = json.load(resp)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # The push service being unreachable must not stop the alarm. The
            # warning is already saved and already visible in the app.
            logger.warning("push service unreachable (%s) - %d devices not reached",
                           exc, len(chunk))
            failed += len(chunk)
            continue

        for token, result in zip(chunk, payload.get("data", [])):
            if result.get("status") == "ok":
                accepted += 1
                continue
            failed += 1
            reason = result.get("message") or result.get("details", {}).get("error", "unknown")
            _mark_invalid(db, token, str(reason)[:200])

    logger.info("push: %d accepted, %d failed", accepted, failed)
    return {"accepted": accepted, "failed": failed}


def _mark_invalid(db: Session, token: str, reason: str) -> None:
    row = db.query(push_token).filter(push_token.token == token).one_or_none()
    if row is not None:
        row.invalid_reason = reason
        db.commit()
        logger.info("push token retired: %s", reason)


def coverage(db: Session) -> dict:
    """How many enrolled people can actually be reached on a phone."""
    total = db.query(push_token).filter(push_token.invalid_reason.is_(None)).count()
    dead = db.query(push_token).filter(push_token.invalid_reason.isnot(None)).count()
    return {"reachable_devices": total, "retired_tokens": dead}
