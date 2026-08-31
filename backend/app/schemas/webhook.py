
from pydantic import BaseModel
from typing import Optional, Literal


class CongestionData(BaseModel):
    timeIntervalStart: str
    timeIntervalStop: str
    congestionLevel: Literal["None", "Low", "Medium", "High"]
    confidenceLevel: int  # 0–100


class CongestionNotification(BaseModel):
    id: str
    source: str           # contains the subscription ID
    type: str
    specversion: str
    datacontenttype: str
    time: str
    data: CongestionData


class GeofencingDevice(BaseModel):
    phone_number: Optional[str] = None
    
    class Config:
        extra = "allow"


class GeofencingArea(BaseModel):
    area_type: Optional[str] = None
    class Config:
        extra = "allow"


class GeofencingData(BaseModel):
    subscriptionId: str
    device: GeofencingDevice
    area: GeofencingArea
    terminationReason: Optional[str] = None


class GeofencingNotification(BaseModel):
    id: str
    source: str
    time: str
    specversion: str
    type: Literal[
        "org.camaraproject.geofencing-subscriptions.v0.area-entered",
        "org.camaraproject.geofencing-subscriptions.v0.area-left",
        "org.camaraproject.geofencing-subscriptions.v0.subscription-ends",
    ]
    datacontenttype: str
    data: GeofencingData


class DualTriggerEvent(BaseModel):
    zone_id: str
    zone_label: str
    tower_cell_id: str
    center_lat: float
    center_lon: float
    radius_m: int
    congestion_device_count: int
    congestion_confidence_avg: float
    entry_rate_per_minute: float
    sampled_phone_numbers: list[str]   # hashed before this point
    triggered_at: str                  # ISO 8601