from pydantic_settings import BaseSettings #to check the settings
from typing import Dict, List # what type of data to expect
import json # to read the shared geography file
import os # to talk with the os
from pathlib import Path # to locate that file relative to this one
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

# Pilot geography.
#
# These used to be hand-written dummy coordinates, and they had drifted into a
# different city from the one the app showed: the backend described Cairo and
# the New Administrative Capital while the UI described a coastal pilot. Two
# sets of coordinates for "the same" zones is the kind of mismatch that only
# shows up when a geofence fires 400 km from the map, so there is now exactly
# one source of truth and both sides read it.
#
# Canonical file: crovia-ui/src/geo/lusail.geo.json
# It lives under the app because Metro bundles JSON from inside its own project
# with no extra config, whereas Python can read any path on disk. Edit the
# geography THERE, never here.

_GEO_PATH = (
    Path(__file__).resolve().parents[2] / "crovia-ui" / "src" / "geo" / "lusail.geo.json"
)

with _GEO_PATH.open(encoding="utf-8") as _f:
    _GEO = json.load(_f)

CITY: dict = _GEO["city"]

# Tier 1. Congestion Insights carries no location of its own, so a device's
# district has to come from somewhere else (a coarse geofence, or its last known
# fix). This is the level congestion gets attributed to.
DISTRICTS: Dict[str, dict] = {d["id"]: d for d in _GEO["districts"]}


def _zone_row(zone: dict) -> dict:
    """Flatten a zone into the shape the existing services already expect."""
    return {
        "zone_id": zone["id"],
        "district_id": zone["district_id"],
        "label": zone["label"],
        "kind": zone["kind"],
        "center_lat": zone["center"]["lat"],
        "center_lon": zone["center"]["lon"],
        "radius_m": zone["radius_m"],
    }


# Tier 2, grouped by their parent district. The name is kept for now so the
# congestion accumulator and subscription manager keep working unchanged, but
# the keys are district ids rather than cell ids: a phone is not bound to one
# tower for the life of a subscription, which is what the old naming implied.
TOWER_ZONE_MAP: Dict[str, List[dict]] = {
    district_id: [_zone_row(z) for z in _GEO["zones"] if z["district_id"] == district_id]
    for district_id in DISTRICTS
}

ZONE_CONFIG_MAP: Dict[str, dict] = {
    zone["zone_id"]: zone
    for zones in TOWER_ZONE_MAP.values()
    for zone in zones
}

