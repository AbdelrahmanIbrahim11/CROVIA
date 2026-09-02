import asyncio
import json
import logging
from typing import List

import network_as_code as nac
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)

def _make_nac_client() -> nac.NetworkAsCodeApi:
    """Initialize the Nokia NaC client."""
    return nac.NetworkAsCodeApi(
        rapidapi_host="network-as-code.nokia.rapidapi.com",
        api_key=settings.nokia_nac_api_key,
    )

async def retrieve_locations_for_devices(phone_numbers: List[str]):
    """
    Calls the Nokia NaC Location Retrieval API for the given list of phone numbers.
    """
    client = _make_nac_client()
    locations = []
    
    for phone in phone_numbers:
        try:
            logger.info(f"Retrieving location for device {phone}")
            
            # Retrieve the location of a device by providing its phone number
            # and the maximum age of the location information in seconds
            location = client.location.retrieve(
                device={"phone_number": phone},
                max_age=3600,
            )
            
            # The location object contains fields for longitude, latitude and radius
            logger.info(f"Location retrieved for {phone}: lon={location.longitude}, lat={location.latitude}, radius={location.radius}")
            locations.append({
                "phone": phone,
                "longitude": location.longitude,
                "latitude": location.latitude,
                "radius": location.radius,
                "last_location_time": location.last_location_time.isoformat() if location.last_location_time else None
            })
            
        except Exception as e:
            logger.error(f"Failed to retrieve location for {phone}: {e}")
            
    return locations

async def location_retrieval_listener(redis: aioredis.Redis):
    """
    Listens to the 'crovia:dual_trigger' Redis channel and triggers Location Retrieval.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe("crovia:dual_trigger")
    logger.info("Started listening for crovia:dual_trigger events")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    zone_id = data.get("zone_id")
                    logger.info(f"Received dual trigger event for zone: {zone_id}")
                    
                    # Extract the sampled phone numbers from the event
                    # Note: These might be hashed, requiring a reverse lookup in a real scenario
                    sampled_phones = data.get("sampled_phone_numbers", [])
                    
                    if sampled_phones:
                        # Proceed with Location Retrieval API call (DBSCAN phase follows this)
                        locations = await retrieve_locations_for_devices(sampled_phones)
                        logger.info(f"Retrieved {len(locations)} locations for zone {zone_id}")
                    else:
                        logger.info(f"No sampled phones provided for zone {zone_id}, skipping location retrieval.")
                        
                except Exception as e:
                    logger.error(f"Error processing dual trigger message: {e}")
    except asyncio.CancelledError:
        logger.info("Location retrieval listener cancelled")
        await pubsub.unsubscribe("crovia:dual_trigger")
