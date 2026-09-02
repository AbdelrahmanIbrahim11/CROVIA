"""
What this does:
  - Receives parsed GeofencingNotification events (area-entered type only)
  - Checks if the zone is currently "armed" (congestion confirmed upstream)
  - Maintains a sliding window of entry events per zone
  - When entry rate crosses GEOFENCE_ENTRY_RATE_THRESHOLD within the window:
       DUAL TRIGGER CONFIRMED
       Selects a random sample of opted-in devices in that zone
       Publishes a DualTriggerEvent to the Redis channel for Location Retrieval

Nokia API reality check:
  - area-entered fires when a subscribed device crosses INTO the geofenced circle
  - area-left fires when it exits — we track these to detect accumulation
    (high entry rate + low exit rate = crowd compressing = danger)
  - Geofencing subscription_id is in data.subscriptionId
  - We maintain our own subscription_id → zone_id map set up at boot
  - phone_number in data.device.phone_number — we hash it immediately
"""

import json
import random
import hashlib
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings, ZONE_CONFIG_MAP
from app.schemas.webhook import GeofencingNotification, DualTriggerEvent


_GEO_SUB_TO_ZONE_KEY = "crovia:geo_sub_zone_map"         # hash: sub_id -- zone_id
_ZONE_ENTRY_WINDOW_KEY = "crovia:geo:entries:{zone_id}"  # sorted set
_ZONE_EXIT_WINDOW_KEY = "crovia:geo:exits:{zone_id}"     # sorted set
_ZONE_DEVICES_KEY = "crovia:zone_devices:{zone_id}"      # set of hashed phones in zone
_TRIGGERED_KEY = "crovia:triggered:{zone_id}"            # cooldown lock


def _hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


async def register_geofencing_subscription(
    redis: aioredis.Redis,
    subscription_id: str,
    zone_id: str,
) -> None:
   
    await redis.hset(_GEO_SUB_TO_ZONE_KEY, subscription_id, zone_id)


async def process_geofencing_event(
    redis: aioredis.Redis,
    notification: GeofencingNotification,
) -> Optional[DualTriggerEvent]:
  
    event_type = notification.type

    if "subscription-ends" in event_type:
        return None

    sub_id = notification.data.subscriptionId
    zone_id = await redis.hget(_GEO_SUB_TO_ZONE_KEY, sub_id)

    if not zone_id:
        return None

    armed_raw = await redis.get(f"crovia:armed:{zone_id}")
    if not armed_raw:
        # Zone is not armed — congestion hasn't confirmed yet; just track passively
        return None

    armed_data: dict = json.loads(armed_raw)
    phone = notification.data.device.phone_number or ""
    hashed_phone = _hash_phone(phone) if phone else ""
    now_ts = datetime.now(timezone.utc).timestamp()

    if "area-entered" in event_type:
        entry_key = _ZONE_ENTRY_WINDOW_KEY.format(zone_id=zone_id)
        member = f"{sub_id}:{now_ts}"
        await redis.zadd(entry_key, {member: now_ts})

        # Track this device as being inside the zone (for sampling later)
        if hashed_phone:
            await redis.sadd(
                _ZONE_DEVICES_KEY.format(zone_id=zone_id),
                hashed_phone,
            )
            await redis.expire(_ZONE_DEVICES_KEY.format(zone_id=zone_id), 300)

        # Trim old entries
        cutoff = now_ts - settings.geofence_rate_window_seconds
        await redis.zremrangebyscore(entry_key, "-inf", cutoff)
        await redis.expire(entry_key, settings.geofence_rate_window_seconds * 3)

    elif "area-left" in event_type:
        exit_key = _ZONE_EXIT_WINDOW_KEY.format(zone_id=zone_id)
        member = f"{sub_id}:{now_ts}"
        await redis.zadd(exit_key, {member: now_ts})

        # Remove device from in-zone set
        if hashed_phone:
            await redis.srem(_ZONE_DEVICES_KEY.format(zone_id=zone_id), hashed_phone)

        cutoff = now_ts - settings.geofence_rate_window_seconds
        await redis.zremrangebyscore(exit_key, "-inf", cutoff)
        await redis.expire(exit_key, settings.geofence_rate_window_seconds * 3)
        return None  # exits alone don't trigger

    entry_key = _ZONE_ENTRY_WINDOW_KEY.format(zone_id=zone_id)
    exit_key = _ZONE_EXIT_WINDOW_KEY.format(zone_id=zone_id)

    entry_count = await redis.zcard(entry_key)
    exit_count = await redis.zcard(exit_key)

    # Entry rate per minute (window may be < 60s at startup, normalise)
    effective_window = min(
        now_ts - (float(armed_data.get("armed_at", now_ts - 1))),
        float(settings.geofence_rate_window_seconds),
    )
    effective_window = max(effective_window, 1.0)
    entry_rate_per_min = (entry_count / effective_window) * 60.0

    if entry_count < settings.geofence_entry_rate_threshold:
        return None

    # Accumulation check: more people entering than leaving = crowd compressing
    if exit_count >= entry_count:
        # Flow is moving through, not accumulating
        return None

    # Cooldown: don't re-trigger the same zone within 5 minutes
    triggered_key = _TRIGGERED_KEY.format(zone_id=zone_id)
    already_triggered = await redis.exists(triggered_key)
    if already_triggered:
        return None

    # Set cooldown lock
    await redis.setex(triggered_key, 300, "1")

    # Sample only the devices that are currently inside the zone
    # AND also reported high congestion to minimize api costs
    high_phones_key = f"crovia:congestion:high_phones:{armed_data['tower_id']}"
    zone_devices_key = _ZONE_DEVICES_KEY.format(zone_id=zone_id)
    
    # sinter finds the overlapping phones that exist in both lists
    target_devices = await redis.sinter(high_phones_key, zone_devices_key)
    all_devices = list(target_devices)
    
    # if the intersection is empty for some reason, fallback to anyone in the zone
    if not all_devices:
        all_devices = list(await redis.smembers(zone_devices_key))

    sample_size = min(settings.location_sample_size, len(all_devices))
    sampled = random.sample(all_devices, sample_size) if sample_size > 0 else []

    zone_cfg = ZONE_CONFIG_MAP.get(zone_id, {})

    event = DualTriggerEvent(
        zone_id=zone_id,
        zone_label=zone_cfg.get("label", zone_id),
        tower_cell_id=armed_data["tower_id"],
        center_lat=zone_cfg.get("center_lat", 0.0),
        center_lon=zone_cfg.get("center_lon", 0.0),
        radius_m=zone_cfg.get("radius_m", 300),
        congestion_device_count=armed_data["device_count"],
        congestion_confidence_avg=armed_data["avg_confidence"],
        entry_rate_per_minute=round(entry_rate_per_min, 2),
        sampled_phone_numbers=sampled,
        triggered_at=datetime.now(timezone.utc).isoformat(),
    )

    # Publish to Redis channel — Location Retrieval stage listens here
    await redis.publish("crovia:dual_trigger", event.model_dump_json())

    return event