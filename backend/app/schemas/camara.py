"""
The real CAMARA notification shapes.

Written against Nokia's documented payloads rather than an idealised version.
The important detail is what a congestion notification does NOT contain: there
is no device identifier and no location anywhere in it. The only thread back to
a device is the subscription id embedded in the `source` URL, which is why the
system has to maintain its own subscription-to-device-to-district map.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


def subscription_id_from_source(source: str) -> str:
    """`.../subscriptions/abc-123` -> `abc-123`."""
    return (source or "").rstrip("/").rsplit("/", 1)[-1]


class CongestionData(BaseModel):
    timeIntervalStart: str | None = None
    timeIntervalStop: str | None = None
    congestionLevel: Literal["None", "Low", "Medium", "High"]
    confidenceLevel: int = 0


class CongestionNotification(BaseModel):
    """
    A congestion notification as the network really sends it.

    Two things differ from the documented shape, both found by receiving a real
    notification from Nokia rather than by reading:

      `data` is a LIST of time intervals, not a single reading. Nokia sends the
      last several windows in one message - four, five minutes apart, oldest
      last. Declaring it as one object made pydantic reject the whole message.

      `source` is the event TYPE, not a URL. It arrives as
      "org.camaraproject.congestioninsights.v0.event", so there is no
      subscription id in it and the notification does not say which device it
      is about at all. That is why each device is given its own webhook
      address, and the device is read from the path instead.
    """

    id: str | None = None
    source: str = ""
    type: str = "event"
    specversion: str = "1.0"
    datacontenttype: str = "application/json"
    time: str | None = None
    data: list[CongestionData] | CongestionData

    @property
    def latest(self) -> CongestionData:
        """
        The most recent reading.

        Nokia orders the list newest first. Taking the newest rather than an
        average matters: averaging four windows would smooth a sudden rise into
        nothing, which is the exact signal the system exists to catch.
        """
        if isinstance(self.data, list):
            if not self.data:
                return CongestionData(congestionLevel="None", confidenceLevel=0)
            return max(self.data, key=lambda d: d.timeIntervalStart or "")
        return self.data

    @property
    def subscription_id(self) -> str:
        return subscription_id_from_source(self.source)


class GeofencingDevice(BaseModel):
    phoneNumber: str | None = None

    class Config:
        extra = "allow"


class GeofencingData(BaseModel):
    subscriptionId: str
    device: GeofencingDevice | None = None
    area: dict | None = None
    terminationReason: str | None = None


class GeofencingNotification(BaseModel):
    id: str | None = None
    source: str = ""
    time: str | None = None
    specversion: str = "1.0"
    datacontenttype: str = "application/json"
    type: str
    data: GeofencingData

    @property
    def event(self) -> str:
        """`org.camaraproject...v0.area-entered` -> `area-entered`."""
        return self.type.rsplit(".", 1)[-1]
