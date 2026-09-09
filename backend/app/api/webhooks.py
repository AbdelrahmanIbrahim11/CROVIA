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

from app.config import settings
from app.runtime import get_engine
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


@router.post("/webhooks/congestion")
async def congestion(notification: CongestionNotification,
                     authorization: str | None = Header(default=None)):
    _check_token(authorization)
    engine = get_engine()
    engine.on_congestion(
        notification.subscription_id,
        notification.data.congestionLevel,
        notification.data.confidenceLevel,
    )
    return {"status": "ok"}


@router.post("/webhooks/geofencing")
async def geofencing(notification: GeofencingNotification, request: Request,
                     authorization: str | None = Header(default=None)):
    _check_token(authorization)
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
