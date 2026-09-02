from fastapi import APIRouter, Depends, HTTPException, Header, Request
from app.config import settings
from app.schemas.webhook import CongestionNotification, GeofencingNotification, AppLocationReport
from app.services.congestion_accumulator import process_congestion_event
from app.services.geofence_rate_counter import process_geofencing_event
from app.db.redis import get_redis

router = APIRouter()

# this function checks if the request comes from nokia by checking the token
def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="missing token")
    
    # usually tokens come as 'bearer my-token' but we just check if our token is in there
    if settings.webhook_auth_token not in authorization:
        raise HTTPException(status_code=401, detail="wrong token")

# this gets the congestion alerts from nokia
@router.post("/webhooks/congestion", dependencies=[Depends(verify_token)])
async def handle_congestion(notification: CongestionNotification):
    redis = await get_redis()
    # pass the event to our accumulator logic
    await process_congestion_event(redis, notification)
    return {"status": "ok"}

# this gets the geofencing alerts from nokia
@router.post("/webhooks/geofencing")
async def handle_geofencing(request: Request, notification: GeofencingNotification):
    # for geofencing nokia uses plain auth in the header or sink credentials
    # so we can check the request headers for our token
    auth_header = request.headers.get("authorization", "")
    if settings.webhook_auth_token not in auth_header:
        raise HTTPException(status_code=401, detail="wrong token")
        
    redis = await get_redis()
    # pass the event to our rate counter logic
    await process_geofencing_event(redis, notification)
    return {"status": "ok"}


# the mobile app calls this endpoint when we wake it up
@router.post("/api/location/heartbeat")
async def handle_app_location(report: AppLocationReport):
    redis = await get_redis()
    # in real life, your backend checks lat/lon to find the zone
    # and then adds it to the congestion accumulator math
    print(f"User {report.phone_number} woke up and is at {report.latitude}, {report.longitude}")
    return {"status": "ok"}
