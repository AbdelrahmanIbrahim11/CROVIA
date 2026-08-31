import datetime
from typing import Optional

import network_as_code as nac
import redis.asyncio as aioredis

from crovia.config.settings import settings, TOWER_ZONE_MAP, ZONE_CONFIG_MAP
from crovia.trigger.congestion_accumulator import register_congestion_subscription
from crovia.trigger.geofence_rate_counter import register_geofencing_subscription


def _make_nac_client() -> nac.NetworkAsCodeApi:
    return nac.NetworkAsCodeApi(
        rapidapi_host="network-as-code.nokia.rapidapi.com",
        api_key=settings.nokia_nac_api_key,
    )


async def bootstrap_subscriptions(
    redis: aioredis.Redis,
    opted_in_devices: list[dict],  # [{"phone_number": "+20...", "tower_cell_id": "tower_cairo_nac_001"}, ...]
) -> dict:

    client = _make_nac_client()
    results = {"congestion": [], "geofencing": [], "errors": []}

    congestion_expire = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1)
    )

    for device in opted_in_devices:
        phone = device["phone_number"]
        tower_id = device["tower_cell_id"]
        try:
            sub = client.congestion_insights.create_subscription(
                device={"phone_number": phone},
                webhook={
                    "notification_url": f"{settings.webhook_base_url}/webhooks/congestion",
                    "notification_auth_token": settings.webhook_auth_token,
                },
                subscription_expire_time=congestion_expire,
            )

            # Store the mapping so process_congestion_event can resolve tower from sub_id
            await register_congestion_subscription(
                redis=redis,
                subscription_id=sub.subscription_id,
                tower_cell_id=tower_id,
                phone_number=phone,
            )

            results["congestion"].append({
                "phone": phone[-4:],   # log only last 4 digits
                "sub_id": sub.subscription_id,
                "tower": tower_id,
                "expires": sub.expires_at.isoformat() if sub.expires_at else None,
            })

        except Exception as e:
            results["errors"].append({"phone": phone[-4:], "error": str(e), "type": "congestion"})

    geo_expire = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1)
    )

    # Collect all unique zones across all towers
    all_zones = list(ZONE_CONFIG_MAP.values())

    for zone in all_zones:
        zone_id = zone["zone_id"]

        # Subscribe to area-entered
        try:
            sub_enter = client.geofencing.create_subscription(
                protocol="HTTP",
                sink=f"{settings.webhook_base_url}/webhooks/geofencing",
                types=["org.camaraproject.geofencing-subscriptions.v0.area-entered"],
                config={
                    "subscription_detail": {
                        # In production: subscribe each opted-in device.
                        # Here we use a representative sentinel for the zone.
                        # The real crowd signal comes from aggregated events.
                        "device": {"phone_number": _zone_sentinel_phone(zone_id)},
                        "area": {
                            "area_type": "CIRCLE",
                            "center": {
                                "latitude": zone["center_lat"],
                                "longitude": zone["center_lon"],
                            },
                            "radius": zone["radius_m"],
                        },
                    },
                    "subscription_expire_time": geo_expire,
                },
                sink_credential={
                    "credential_type": "PLAIN",
                    "identifier": "crovia",
                    "secret": settings.webhook_auth_token,
                },
            )

            await register_geofencing_subscription(
                redis=redis,
                subscription_id=sub_enter.id,
                zone_id=zone_id,
            )

            # Subscribe to area-left for same zone (separate subscription per Nokia docs)
            sub_exit = client.geofencing.create_subscription(
                protocol="HTTP",
                sink=f"{settings.webhook_base_url}/webhooks/geofencing",
                types=["org.camaraproject.geofencing-subscriptions.v0.area-left"],
                config={
                    "subscription_detail": {
                        "device": {"phone_number": _zone_sentinel_phone(zone_id)},
                        "area": {
                            "area_type": "CIRCLE",
                            "center": {
                                "latitude": zone["center_lat"],
                                "longitude": zone["center_lon"],
                            },
                            "radius": zone["radius_m"],
                        },
                    },
                    "subscription_expire_time": geo_expire,
                },
                sink_credential={
                    "credential_type": "PLAIN",
                    "identifier": "crovia",
                    "secret": settings.webhook_auth_token,
                },
            )

            await register_geofencing_subscription(
                redis=redis,
                subscription_id=sub_exit.id,
                zone_id=zone_id,
            )

            results["geofencing"].append({
                "zone_id": zone_id,
                "sub_enter_id": sub_enter.id,
                "sub_exit_id": sub_exit.id,
                "radius_m": zone["radius_m"],
            })

        except Exception as e:
            results["errors"].append({"zone_id": zone_id, "error": str(e), "type": "geofencing"})

    return results


def _zone_sentinel_phone(zone_id: str) -> str:

    # In production: query consent store for opted-in users in this zone's
    # geographic area and subscribe each of them individually.
    zone_index = list(ZONE_CONFIG_MAP.keys()).index(zone_id) + 1
    return f"+9999900{zone_index:04d}"


async def refresh_expiring_subscriptions(
    redis: aioredis.Redis,
    opted_in_devices: list[dict],
) -> None:

    await bootstrap_subscriptions(redis, opted_in_devices)