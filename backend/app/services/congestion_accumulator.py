import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from crovia.config.settings import settings, TOWER_ZONE_MAP
from crovia.models.webhooks import CongestionNotification


# these are just the key names we use to store stuff in redis
#  as labels on different boxes
_TOWER_WINDOW_KEY = "crovia:congestion:window:{tower_id}"   # sorted set (score=timestamp)
_TOWER_CONFIDENCE_KEY = "crovia:congestion:confidence:{tower_id}"  # list of confidence values
_ARMED_ZONES_KEY = "crovia:armed_zones"                     # set of currently-armed zone IDs
_SUB_TO_TOWER_KEY = "crovia:sub_tower_map"                  # hash: subscription_id -- tower_id
_ZONE_DEVICES_KEY = "crovia:zone_devices:{zone_id}"         # set of hashed phone numbers in zone


def _extract_subscription_id(source: str) -> str:
    # nokia sends the subscription id at the end of a url like ".../subs/abc123"
    # we just grab the last part after the final slash
    return source.rstrip("/").split("/")[-1]


def _hash_phone(phone: str) -> str:
    # we never store the real phone number anywhere
    # sha256 turns it into a random looking string, we only keep the first 16 chars
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


async def register_congestion_subscription(
    redis: aioredis.Redis,
    subscription_id: str,
    tower_cell_id: str,
    phone_number: str,
) -> None:

    # link this subscription id to the tower so we can look it up later when nokia sends an event
    await redis.hset(_SUB_TO_TOWER_KEY, subscription_id, tower_cell_id)
    # store the hashed phone under the tower so we can sample it later if a trigger fires
    await redis.sadd(f"crovia:tower_devices:{tower_cell_id}", _hash_phone(phone_number))


async def process_congestion_event(
    redis: aioredis.Redis,
    notification: CongestionNotification,
) -> Optional[list[str]]:

    level = notification.data.congestionLevel
    confidence = notification.data.confidenceLevel

    # we only care about high congestion, anything less is not dangerous enough
    if level != "High":
        return None

    # nokia's congestion readings are predictive so they can be wrong
    # below 50% confidence we just ignore it to avoid false alarms
    if confidence < 50:
        return None

    sub_id = _extract_subscription_id(notification.source)

    # use the sub id to find out which tower this event came from
    tower_id = await redis.hget(_SUB_TO_TOWER_KEY, sub_id)
    if not tower_id:
        # sub id we don't recognize, probably stale or from another service
        return None

    # check if this tower is actually mapped to any of our zones
    # if it's not in our map we don't know what to do with it
    if tower_id not in TOWER_ZONE_MAP:
        return None

    now_ts = datetime.now(timezone.utc).timestamp()
    window_key = _TOWER_WINDOW_KEY.format(tower_id=tower_id)
    conf_key = _TOWER_CONFIDENCE_KEY.format(tower_id=tower_id)

    # add this event into the sorted set using the current timestamp as the score
    # this lets redis keep events ordered by time automatically
    member = f"{sub_id}:{now_ts}"
    await redis.zadd(window_key, {member: now_ts})

    # also save the confidence value separately so we can average it later
    await redis.lpush(conf_key, confidence)

    # remove any events that are older than our window (e.g. older than 30 seconds)
    # this is the "sliding window" — we only look at recent events
    cutoff = now_ts - settings.congestion_window_seconds
    await redis.zremrangebyscore(window_key, "-inf", cutoff)

    # set an expiry on the redis key so it deletes itself if the tower goes quiet
    # using 3x the window as a safe buffer
    await redis.expire(window_key, settings.congestion_window_seconds * 3)

    # cap the confidence list to 100 entries so it doesn't grow forever
    await redis.ltrim(conf_key, 0, 99)

    # how many unique devices reported high congestion in the last window
    device_count = await redis.zcard(window_key)

    # not enough devices yet to be sure there's a real crowd problem
    if device_count < settings.congestion_device_threshold:
        return None

    # we hit the threshold — enough devices confirmed congestion at this tower
    # now we find all the zones that are under this tower's coverage
    zones = TOWER_ZONE_MAP[tower_id]
    zone_ids = [z["zone_id"] for z in zones]

    # grab all saved confidence values and average them
    # this gives us a single quality score for how reliable this alarm is
    all_conf = await redis.lrange(conf_key, 0, -1)
    avg_confidence = sum(int(c) for c in all_conf) / len(all_conf) if all_conf else float(confidence)

    # mark each zone as "armed" in redis
    # armed means: congestion is confirmed, if geofencing also fires → dual trigger
    # the key expires automatically so zones disarm themselves if congestion drops
    arm_ttl = settings.congestion_window_seconds * 4
    for zone_id in zone_ids:
        await redis.setex(
            f"crovia:armed:{zone_id}",
            arm_ttl,
            json.dumps({
                "tower_id": tower_id,
                "device_count": device_count,
                "avg_confidence": round(avg_confidence, 1),
                "armed_at": now_ts,  # geofence counter uses this to normalize the entry rate
            }),
        )

    # return the list of armed zone ids so the caller knows what got triggered
    return zone_ids