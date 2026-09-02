
from pydantic import BaseModel # for type-checking
from typing import Optional, Literal

# nokai will send a big json data so we need to filter it out 
# so we map it into smaller boxes but what nokia send exactly ? 
#  nokia sends a json block that matches these classes exactly
#  it looks something like {"id": "123", "type": "event", "data": {"congestionLevel": "High"}}

class CongestionData(BaseModel):
    timeIntervalStart: str
    timeIntervalStop: str
    congestionLevel: Literal["None", "Low", "Medium", "High"]
    confidenceLevel: int  # 0–100


class CongestionNotification(BaseModel):
    id: str # nokia id for that specific notification 
    source: str           
    #  nokia sends a web address here ending with an id like /subs/12345
    #  our app chops off the end to get that 12345 id
    type: str # putting this back so the app does not crash
    specversion: str # some formatting stuff 


class AppLocationReport(BaseModel):
    # this is the message the mobile app sends us when it wakes up
    phone_number: str
    latitude: float
    longitude: float
    timestamp: str
    datacontenttype: str # some formatting stuff
    time: str # what does it mean with bad signal 
    # this is just the exact timestamp like 12:05 PM when nokia noticed the bad signal
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
    subscriptionId: str # what is that ?
    # this is the receipt id nokia gave us when we asked them to draw the geofence
    # it tells the app exactly which zone the person walked into
    device: GeofencingDevice
    area: GeofencingArea
    terminationReason: Optional[str] = None # what is that ?
    # if nokia stops watching the zone (like if the 24 hour timer ran out) they tell us why here


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
    #  it is just nokia's way of telling us the 24 hour timer expired and they stopped watching the geofence
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