"""
Example: Using the Network as Code (Nokia) Congestion Insights API
to monitor congestion levels for one or more devices, both via
webhook subscription and via direct polling.

NOTE: Only methods/fields/parameters that appear in the official
documentation are used with confidence. Anything not explicitly
documented is marked with a comment.
"""

from datetime import datetime, timezone, timedelta
from network_as_code import NetworkAsCodeApi

# --- Client setup (documented) ---
client = NetworkAsCodeApi(
    rapidapi_host="network-as-code.nokia.rapidapi.com",
    api_key="YOUR_API_KEY",
)

# --- Devices to monitor (custom data structure, NOT part of the API itself) ---
devices = [
    {"name": "responder_1", "phone_number": "+999991234567"},
    {"name": "responder_2", "phone_number": "+999991234568"},
]

# Dictionaries to keep track of subscriptions (custom, not part of the API)
active_subscriptions = {}


def subscribe_device_to_congestion(device: dict):
    """
    Creates a congestion subscription for one device.
    IMPORTANT: This step is mandatory before polling or querying
    congestion data for this device — the docs state the subscription
    itself triggers congestion metrics collection.
    """
    subscription = client.congestion_insights.create_subscription(
        device={"phone_number": device["phone_number"]},  # documented
        webhook={
            "notification_url": "https://your-backend.com/webhooks/congestion",  # documented
            "notification_auth_token": "my-secret-token",  # documented, optional
        },
        subscription_expire_time=datetime.now(timezone.utc) + timedelta(days=1),  # documented, mandatory
    )
    print(f"Subscribed {device['name']} — subscription_id: {subscription.subscription_id}")
    print(f"Starts at: {subscription.starts_at}")
    print(f"Expires at: {subscription.expires_at}")
    return subscription


def subscribe_all_devices():
    """Loop through devices and create a congestion subscription for each (custom logic)."""
    for device in devices:
        sub = subscribe_device_to_congestion(device)
        active_subscriptions[device["name"]] = sub
    return active_subscriptions


def poll_current_congestion(phone_number: str):
    """
    Polls the current congestion level for a device.
    NOTE: requires an active subscription for this device to already exist.
    """
    congestion = client.congestion_insights.query(
        device={"phone_number": phone_number},  # documented
    )
    # Returns a list of congestion level objects (documented)
    if congestion:
        first = congestion[0]
        print(f"Current congestion level: {first.level}")
        return first
    else:
        # NOTE: the docs don't specify what happens if the list is empty
        # (e.g. no data yet available) — handling this defensively.
        print("No congestion data returned.")
        return None


def get_congestion_forecast(phone_number: str, hours_ahead: int = 3):
    """
    Fetches predicted congestion data for a future time window.
    """
    congestion_data = client.congestion_insights.query(
        device={"phone_number": phone_number},  # documented
        start=datetime.now(timezone.utc),  # documented, optional
        end=datetime.now(timezone.utc) + timedelta(hours=hours_ahead),  # documented, optional
    )

    results = []
    for event in congestion_data:
        entry = {
            "start": event.time_interval_start.isoformat(),
            "stop": event.time_interval_stop.isoformat(),
            "level": event.congestion_level,
            "confidence": event.confidence_level,  # documented: relevant for predictions
        }
        results.append(entry)
        print(entry)

    return results


def get_congestion_history(phone_number: str, hours_back: int = 3):
    """
    Fetches historical congestion data for a past time window.
    NOTE: The documentation only shows a future-window example explicitly.
    Using a past start/end here follows the general description that
    'start'/'end' can retrieve historical data, but no dedicated
    historical-data code example is given in the source.
    """
    congestion_data = client.congestion_insights.query(
        device={"phone_number": phone_number},
        start=datetime.now(timezone.utc) - timedelta(hours=hours_back),
        end=datetime.now(timezone.utc),
    )
    return list(congestion_data)


def list_all_subscriptions():
    """Fetch all currently active congestion subscriptions (documented method)."""
    return client.congestion_insights.list_subscriptions()


def get_subscription_by_id(resource_id: str):
    """Fetch a single congestion subscription by its ID (documented method)."""
    return client.congestion_insights.get_subscription(resource_id)


def unsubscribe_device(resource_id: str):
    """Delete/terminate a congestion subscription (documented method)."""
    client.congestion_insights.delete_subscription(resource_id=resource_id)


# --- Example: handling an incoming webhook notification ---
# The documentation's own example uses FastAPI, so this follows the
# same framework rather than substituting a different one.
from fastapi import FastAPI, Header
from pydantic import BaseModel
from typing_extensions import Annotated
from typing import Union

app = FastAPI()


class Data(BaseModel):
    level: str
    # NOTE: The raw JSON schema shown in the docs uses different field
    # names (timeIntervalStart, timeIntervalStop, congestionLevel,
    # confidenceLevel) than this minimal handler model (`level`).
    # The docs show two slightly different shapes for the notification
    # payload in different sections — this class mirrors the simpler
    # handler example, not the full JSON schema example.


class Notification(BaseModel):
    id: str
    source: str
    type: str
    specversion: str
    datacontenttype: str
    time: str
    data: Data


@app.post("/webhooks/congestion")
def receive_congestion_notification(
    notification: Notification,
    authorization: Annotated[Union[str, None], Header] = None,
):
    # Documented: auth token is expected as "Bearer <token>" in the
    # Authorization header.
    if authorization == "Bearer my-secret-token":
        print(f"Congestion update received: {notification.data.level}")
        # TODO: trigger your crowd-safety logic / agent here
    else:
        # NOTE: the docs don't specify what response code/behavior is
        # expected on auth failure — returning nothing here is a gap.
        print("Unauthorized notification received — ignoring.")


if __name__ == "__main__":
    # Step 1: subscribe devices (mandatory before polling/querying)
    subscribe_all_devices()

    # Step 2: poll current congestion for one device
    poll_current_congestion(devices[0]["phone_number"])

    # Step 3: get a 3-hour congestion forecast
    get_congestion_forecast(devices[0]["phone_number"], hours_ahead=3)

    # Step 4: list active subscriptions
    print(list_all_subscriptions())

    # Run the webhook receiver
    # NOTE: run with `uvicorn this_file:app` as shown in the docs —
    # host/port/reload flags here are standard uvicorn usage, not
    # part of the Congestion Insights API itself.
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)