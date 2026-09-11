"""
Where Nokia's notifications arrive.

These now feed the live detection engine. They previously called the earlier
services, which were replaced but left wired in, so the running system was
still executing the design that was superseded.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from app.config import settings
from app.runtime import get_engine
from app.services import priority
from app.usersDB.db import getdb
from app.schemas.camara import CongestionNotification, GeofencingNotification

logger = logging.getLogger("crovia.webhooks")
router = APIRouter(tags=["webhooks"])


def _check_token(authorization: str | None) -> None:
    """
    Compare the bearer token in constant time.

    The previous check asked whether the secret appeared anywhere in the header,
    which accepts any string that happens to contain it and leaks length through
    timing.
    """
    expected = settings.webhook_auth_token or ""
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization header")
    token = authorization.split(" ", 1)[-1].strip()
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="bad token")


@router.post("/webhooks/congestion/{device_key}")
@router.post("/webhooks/congestion")
async def congestion(request: Request, device_key: str | None = None,
                     authorization: str | None = Header(default=None)):
    """
    A congestion notification from the network.

    The body is read and validated by hand rather than declared as a typed
    parameter. FastAPI would reject a mismatched payload with 422 before any of
    our code ran, and the body would never be logged - so a notification whose
    shape differs from the documentation would be dropped in silence, and a
    system receiving nothing looks exactly like a calm city.

    Nokia also sends lifecycle events on the same address, such as the
    confirmation that a subscription has started. Those carry no congestion
    level and are acknowledged rather than treated as an error.
    """
    _check_token(authorization)
    body = await request.json()

    event_type = str(body.get("type", ""))
    if "subscription-started" in event_type or "subscription-ends" in event_type:
        logger.info("congestion subscription lifecycle event: %s", event_type)
        return {"status": "ok", "note": "lifecycle event acknowledged"}

    try:
        notification = CongestionNotification.model_validate(body)
    except ValidationError as exc:
        # Logged in full, because this is the only way to learn what the
        # network really sends when it differs from the documentation.
        logger.warning("congestion notification did not match the expected shape: %s\n"
                       "body was: %s", exc.errors()[:3], body)
        return {"status": "ignored", "reason": "unrecognised payload"}

    reading = notification.latest
    engine = get_engine()

    # Which device this is about comes from the ADDRESS, not the body.
    #
    # A real notification carries no device and no subscription id - `source`
    # is the event type. Each device is therefore subscribed with its own
    # webhook path, and that path is the only thing that identifies it.
    if device_key:
        engine.on_congestion_device(device_key, reading.congestionLevel,
                                    reading.confidenceLevel)
    else:
        # An older subscription made before per-device addresses existed. It
        # cannot be attributed, so it is counted and dropped rather than
        # guessed at.
        logger.warning("congestion notification with no device in the path - "
                       "the subscription predates per-device webhooks and "
                       "cannot be attributed")
    return {"status": "ok"}


@router.post("/webhooks/geofencing/{device_key}")
@router.post("/webhooks/geofencing")
async def geofencing(request: Request, device_key: str | None = None,
                     authorization: str | None = Header(default=None)):
    """Same reasoning as the congestion handler above."""
    _check_token(authorization)
    body = await request.json()

    try:
        notification = GeofencingNotification.model_validate(body)
    except ValidationError as exc:
        logger.warning("geofence notification did not match the expected shape: %s\n"
                       "body was: %s", exc.errors()[:3], body)
        return {"status": "ignored", "reason": "unrecognised payload"}

    engine = get_engine()
    event = notification.event
    if event == "subscription-ends":
        # A subscription that has ended and is not replaced means the system
        # quietly stops receiving events for that device, which looks exactly
        # like a calm city.
        logger.warning("subscription ended (%s) for %s",
                       notification.data.terminationReason, notification.data.subscriptionId)
        engine.on_subscription_end(notification.data.subscriptionId)
    else:
        engine.on_geofence(notification.data.subscriptionId, event)
    return {"status": "ok"}


@router.post("/webhooks/qod")
async def qod_status(request: Request,
                     authorization: str | None = Header(default=None)):
    """
    The network telling us what happened to a priority session.

    A session starts REQUESTED and becomes AVAILABLE only once resources are
    actually allocated. The network can also take it back on its own, which
    arrives here as UNAVAILABLE with NETWORK_TERMINATED - and that is the only
    way to find out. A system that assumes priority is active because it asked
    for it will be wrong at some point, during an incident.
    """
    _check_token(authorization)
    body = await request.json()
    data = body.get("data") or {}
    session_id = data.get("sessionId")
    if not session_id:
        logger.warning("qod notification with no session id: %s", body)
        return {"status": "ignored"}

    db = next(getdb())
    try:
        known = priority.on_status_change(db, session_id,
                                          data.get("qosStatus", "UNKNOWN"),
                                          data.get("statusInfo"))
    finally:
        db.close()
    if not known:
        logger.info("qod notification for a session we do not know: %s", session_id)
    return {"status": "ok"}
