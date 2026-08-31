import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from crovia.config.settings import settings, TOWER_ZONE_MAP
from crovia.models.webhooks import CongestionNotification


# redis key namespaces
_TOWER_WINDOW_KEY = "crovia:congestion:window:{tower_id}"   # sorted set (score=timestamp)
_TOWER_CONFIDENCE_KEY = "crovia:congestion:confidence:{tower_id}"  # list of confidence values
_ARMED_ZONES_KEY = "crovia:armed_zones"                     # set of currently-armed zone IDs
_SUB_TO_TOWER_KEY = "crovia:sub_tower_map"                  # hash: subscription_id -- tower_id
_ZONE_DEVICES_KEY = "crovia:zone_devices:{zone_id}"         # set of hashed phone numbers in zone


def _extract_subscription_id(source: str) -> str:
    return source.rstrip("/").split("/")[-1]


def _hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


async def register_congestion_subscription(
    redis: aioredis.Redis,
    subscription_id: str,
    tower_cell_id: str,
    phone_number: str,
) -> None:

    await redis.hset(_SUB_TO_TOWER_KEY, subscription_id, tower_cell_id)
    #hashed phone under tower for sampling at trigger time
    await redis.sadd(f"crovia:tower_devices:{tower_cell_id}", _hash_phone(phone_number))


async def process_congestion_event(
    redis: aioredis.Redis,
    notification: CongestionNotification,
) -> Optional[list[str]]:

    level = notification.data.congestionLevel
    confidence = notification.data.confidenceLevel

    if level != "High":
        return None

    # minimum confidence guard -- predictive results can be low quality
    if confidence < 50:
        return None

    sub_id = _extract_subscription_id(notification.source)

    # resolve tower cell ID from subscription
    tower_id = await redis.hget(_SUB_TO_TOWER_KEY, sub_id)
    if not tower_id:
        return None

    if tower_id not in TOWER_ZONE_MAP:
        return None

    now_ts = datetime.now(timezone.utc).timestamp()
    window_key = _TOWER_WINDOW_KEY.format(tower_id=tower_id)
    conf_key = _TOWER_CONFIDENCE_KEY.format(tower_id=tower_id)

    # Add this device's event to the sorted set (score = timestamp, member = sub_id + timestamp)
    member = f"{sub_id}:{now_ts}"
    await redis.zadd(window_key, {member: now_ts})
    await redis.lpush(conf_key, confidence)

    # Trim entries older than the window
    cutoff = now_ts - settings.congestion_window_seconds
    await redis.zremrangebyscore(window_key, "-inf", cutoff)

    # Set TTL so keys auto-clean (window * 3 is safe)
    await redis.expire(window_key, settings.congestion_window_seconds * 3)
    await redis.ltrim(conf_key, 0, 99)  # keep last 100 confidence values

    # Count distinct devices in window
    device_count = await redis.zcard(window_key)

    if device_count < settings.congestion_device_threshold:
        return None

    # Threshold crossed — arm the zones for this tower
    zones = TOWER_ZONE_MAP[tower_id]
    zone_ids = [z["zone_id"] for z in zones]

    # Compute average confidence for this tower's current window
    all_conf = await redis.lrange(conf_key, 0, -1)
    avg_confidence = sum(int(c) for c in all_conf) / len(all_conf) if all_conf else float(confidence)

    # Mark zones as armed in Redis with TTL (auto-disarm after inactivity)
    arm_ttl = settings.congestion_window_seconds * 4
    for zone_id in zone_ids:
        await redis.setex(
            f"crovia:armed:{zone_id}",
            arm_ttl,
            json.dumps({
                "tower_id": tower_id,
                "device_count": device_count,
                "avg_confidence": round(avg_confidence, 1),
                "armed_at": now_ts,
            }),
        )

    return zone_ids