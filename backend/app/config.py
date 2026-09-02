from pydantic_settings import BaseSettings #to check the settings
from typing import Dict, List # what type of data to expect 
import os # to talk with the os
from dotenv import load_dotenv

load_dotenv() # load from .env
# where is that environment and what passwords u talk about ?
# answer: it looks for a hidden .env file on your computer to securely load your secret keys


class Settings(BaseSettings):
    nokia_nac_api_key: str = os.getenv("NOKIA_NAC_API_KEY", "") 
    # the password to ask nokia about things
    # but password for what exactly ? 
    # answer: this proves to nokia who is asking for the api request so they know who to bill
    webhook_base_url: str = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")
    # where nokia sends the data to us 
    webhook_auth_token: str = os.getenv("WEBHOOK_AUTH_TOKEN", "change-me")
    # secret handshake nokia
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # address for the fasr memory database

    # trigger thresholds
    # needs to be looked into again
    # the fisrt two lines to indicate the congestion design decision for the threshold
    congestion_window_seconds: int = int(os.getenv("CONGESTION_WINDOW_SECONDS", "30"))
    congestion_device_threshold: int = int(os.getenv("CONGESTION_DEVICE_THRESHOLD", "15"))
    geofence_entry_rate_threshold: int = int(os.getenv("GEOFENCE_ENTRY_RATE_THRESHOLD", "8"))
    geofence_rate_window_seconds: int = int(os.getenv("GEOFENCE_RATE_WINDOW_SECONDS", "60"))
    # are those entry rate and rate window are applied onto for example the three zones assigfned to one tower 
    # and i mean every one enter or exit or traverse through those three zones will count ? 
    # answer: these numbers apply strictly to one single zone not the sum of all zones on a tower
    # answer: 8 people must enter one specific zone within 60 seconds to fire the alarm
    location_sample_size: int = int(os.getenv("LOCATION_SAMPLE_SIZE", "20"))
    # it is the most expensive one so it should be random sampled


settings = Settings()

# dummy towers 
# each tower has an assigned zones

TOWER_ZONE_MAP: Dict[str, List[dict]] = {
    "tower_cairo_nac_001": [
        {
            "zone_id": "zone_stadium_east_exit",
            "label": "Stadium east exit corridor",
            "center_lat": 30.0626,
            "center_lon": 31.2497,
            "radius_m": 300,
        },
        {
            "zone_id": "zone_market_north_alley",
            "label": "North market alley entrance",
            "center_lat": 30.0641,
            "center_lon": 31.2511,
            "radius_m": 250,
        },
    ],
    "tower_cairo_nac_002": [
        {
            "zone_id": "zone_bridge_underpass",
            "label": "Bridge underpass bottleneck",
            "center_lat": 30.0558,
            "center_lon": 31.2389,
            "radius_m": 200,
        },
    ],
    "tower_new_admin_001": [
        {
            "zone_id": "zone_gov_district_gate_a",
            "label": "Government district gate A",
            "center_lat": 30.0233,
            "center_lon": 31.7362,
            "radius_m": 400,
        },
        {
            "zone_id": "zone_gov_district_gate_b",
            "label": "Government district gate B",
            "center_lat": 30.0219,
            "center_lon": 31.7389,
            "radius_m": 350,
        },
    ],
}

ZONE_CONFIG_MAP: Dict[str, dict] = {
    zone["zone_id"]: zone
    for zones in TOWER_ZONE_MAP.values()
    for zone in zones
}

