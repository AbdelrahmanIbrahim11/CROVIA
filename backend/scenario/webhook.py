"""
Delivering notifications the way Nokia delivers them.

The payloads here are the real CAMARA CloudEvents shapes, not tidied-up
versions, because the shape is where the traps are. Two of them were only found
by receiving a genuine notification from Nokia:

  `data` on a congestion notification is a LIST of recent time windows, newest
  first - not a single reading. Declared as one object, pydantic rejected the
  whole message and the system silently received nothing.

  `source` is the event TYPE, not a URL. There is no subscription id anywhere
  in the body, so the message does not say which device it concerns. The
  webhook ADDRESS is the only thing that identifies the device, which is why
  every device is given its own path ending in its hash.

Delivery goes through the app's real HTTP endpoints, with the real bearer
token, so the parsing, the authentication and the attribution are all exercised
exactly as they are in production. Nothing here reaches into the engine.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

from app.core.registry import hash_phone


def _now_iso(offset_s: float = 0.0) -> str:
    return (dt.datetime.now(dt.timezone.utc)
            + dt.timedelta(seconds=offset_s)).isoformat()


class Delivery:
    """
    Posts notifications into the running app.

    Two modes, and the difference matters when reading results.

    HTTP MODE (`client` given) sends a real request to the real webhook
    endpoint. Authentication, CloudEvents parsing, the list-shaped `data`
    field and per-device attribution by URL are all exercised exactly as in
    production. This is the honest mode and it is what scenario/run.py uses.

    DIRECT MODE (`engine` given) hands the reading to the engine without an
    HTTP round trip. It exists for the live demonstration running INSIDE the
    service, where posting to yourself from your own event loop is awkward and
    buys nothing: the webhook path is already proven by the HTTP mode, and what
    a demonstration needs to show is the detection, not the plumbing.

    Anything that only works in direct mode would be a result that does not
    survive contact with the real network, so nothing is allowed to differ
    between them except the transport.
    """

    def __init__(self, client=None, token: str | None = None, engine=None) -> None:
        self.client = client
        self.engine = engine
        self.token = token or os.getenv("WEBHOOK_AUTH_TOKEN", "scenario-token")
        self.delivered = 0
        self.rejected = 0

    def _post(self, path: str, body: dict) -> None:
        if self.client is None:
            return
        r = self.client.post(
            path, json=body,
            headers={"Authorization": f"Bearer {self.token}"})
        if getattr(r, "status_code", 500) == 200:
            self.delivered += 1
        else:
            self.rejected += 1

    # ---- congestion ------------------------------------------------------

    def congestion(self, sink: str, phone: str, level: str,
                   confidence: int, now: float) -> None:
        """
        One congestion notification.

        Carries no device identifier and no location, exactly as documented.
        Several recent windows are included, newest first, and CROVIA is
        expected to take the newest rather than average them - averaging would
        smooth a sudden rise into nothing, which is the one signal that matters.
        """
        hashed = hash_phone(phone)
        body = {
            "id": str(uuid.uuid4()),
            # The event type, NOT a URL. There is no id to extract from it.
            "source": "org.camaraproject.congestioninsights.v0.event",
            "type": "org.camaraproject.congestioninsights.v0.event",
            "specversion": "1.0",
            "datacontenttype": "application/json",
            "time": _now_iso(),
            "data": [
                {"timeIntervalStart": _now_iso(-300),
                 "timeIntervalStop": _now_iso(0),
                 "congestionLevel": level,
                 "confidenceLevel": confidence},
                {"timeIntervalStart": _now_iso(-600),
                 "timeIntervalStop": _now_iso(-300),
                 "congestionLevel": "Low",
                 "confidenceLevel": max(40, confidence - 20)},
            ],
        }
        if self.engine is not None:
            # Same reading, same filter, no HTTP. The engine cannot tell.
            self.engine.on_congestion_device(hashed, level, confidence)
            self.delivered += 1
            return
        self._post(f"/webhooks/congestion/{hashed}", body)

    # ---- geofencing ------------------------------------------------------

    def geofence(self, sink: str, sub_id: str, phone: str,
                 area_id: str, event: str) -> None:
        """
        One geofence notification.

        Unlike congestion, this one DOES name the device and the subscription.
        Only area-entered is ever sent, because that is the only event type
        subscribed to.
        """
        hashed = hash_phone(phone)
        body = {
            "id": str(uuid.uuid4()),
            "source": f"https://nokia.example/geofencing/subscriptions/{sub_id}",
            "type": f"org.camaraproject.geofencing-subscriptions.v0.{event}",
            "specversion": "1.0",
            "datacontenttype": "application/json",
            "time": _now_iso(),
            "data": {
                "subscriptionId": sub_id,
                "device": {"phoneNumber": phone},
                "area": {"areaType": "CIRCLE"},
            },
        }
        if self.engine is not None:
            self.engine.on_geofence(sub_id, event)
            self.delivered += 1
            return
        self._post(f"/webhooks/geofencing/{hashed}", body)
