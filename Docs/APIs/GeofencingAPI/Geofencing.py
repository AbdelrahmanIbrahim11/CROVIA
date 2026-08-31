"""
Example: Using the Network as Code (Nokia) Geofencing API
to monitor multiple crowd zones with a 100m radius circle each.

NOTE: Only methods/fields/parameters that appear in the official
documentation are used with confidence. Anything not explicitly
documented is marked with a comment.
"""

import datetime
from network_as_code import NetworkAsCodeApi

# --- Client setup (documented) ---
client = NetworkAsCodeApi(
    rapidapi_host="network-as-code.nokia.rapidapi.com",
    api_key="YOUR_API_KEY",
)

# --- Zones to monitor (custom data structure, NOT part of the API itself) ---
# This list is just our own way of organizing zones before looping over them.
zones = [
    {"name": "tahrir_square", "lat": 30.044420, "lon": 31.235712, "device": "+201000000001"},
    {"name": "corniche_alex", "lat": 31.200092, "lon": 29.918739, "device": "+201000000002"},
]

# Dictionary to keep track of created subscriptions (custom, not part of the API)
active_subscriptions = {}


def create_zone_subscription(zone: dict):
    """
    Creates a geofencing subscription for one zone.
    Uses documented parameters only.
    """
    subscription = client.geofencing.create_subscription(
        protocol="HTTP",  # documented: only HTTP is currently allowed
        sink="https://your-backend.com/webhooks/geofencing",  # documented: your webhook URL
        types=["org.camaraproject.geofencing-subscriptions.v0.area-entered"],  # documented event type
        config={
            "subscription_detail": {
                "device": {
                    "phone_number": zone["device"]  # documented: device identified by phone_number
                    # NOTE: the doc does not specify other possible device identifier
                    # formats (e.g. IP address, IMSI) for this endpoint — only
                    # phone_number appears in the given examples.
                },
                "area": {
                    "area_type": "CIRCLE",       # documented
                    "center": {
                        "latitude": zone["lat"],
                        "longitude": zone["lon"],
                    },
                    "radius": 100,  # documented field; NOTE: doc warns small radii
                                    # may be inaccurate (cell-tower-level accuracy)
                                    # and some countries enforce a minimum radius
                                    # (exact minimum value is NOT documented here)
                },
            },
            "subscription_expire_time": (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=1)
            ),  # documented, optional
            "subscription_max_events": 50,  # documented, optional
            "initial_event": False,  # documented, optional — True would fire
                                      # an immediate event reflecting current state
        },
        # sink_credential is optional and documented; omitted here since
        # we're not using authentication in this example.
        # sink_credential={
        #     "credential_type": "PLAIN",  # documented option
        #     "identifier": "client-id",
        #     "secret": "client-secret",
        # },
    )
    return subscription


def create_all_zone_subscriptions():
    """Loop through zones and create a subscription for each (custom logic)."""
    for zone in zones:
        sub = create_zone_subscription(zone)
        active_subscriptions[zone["name"]] = sub
        print(f"Subscribed to zone: {zone['name']}")
    return active_subscriptions


def list_all_subscriptions():
    """Fetch all currently active subscriptions (documented method)."""
    return client.geofencing.list_subscriptions()


def get_subscription_by_id(subscription_id: str):
    """Fetch a single subscription by its ID (documented method)."""
    return client.geofencing.get_subscription(subscription_id=subscription_id)


def delete_zone_subscription(subscription_id: str):
    """Delete/terminate a subscription manually (documented method)."""
    client.geofencing.delete_subscription(subscription_id)


# --- Example: handling an incoming webhook notification ---
# NOTE: This is NOT part of the network_as_code SDK itself — it's a plain
# example of a Flask endpoint you would write yourself to receive the
# POST requests the API sends to your `sink` URL.
from flask import Flask, request, jsonify  # not part of the geofencing API

app = Flask(__name__)


@app.route("/webhooks/geofencing", methods=["POST"])
def handle_geofencing_notification():
    payload = request.get_json()

    event_type = payload.get("type")  # documented field
    data = payload.get("data", {})    # documented field
    subscription_id = data.get("subscriptionId")  # documented field
    device_info = data.get("device")  # documented field exists, but its
                                       # internal structure/content (e.g. what
                                       # keys are inside "device") is NOT
                                       # specified in the documentation
    area_info = data.get("area")      # documented field, structure not detailed
                                       # beyond what was used at subscription time

    if event_type == "org.camaraproject.geofencing-subscriptions.v0.area-entered":
        print(f"Device entered zone. Subscription: {subscription_id}")
        # TODO: trigger your crowd-safety logic / agent here
    elif event_type == "org.camaraproject.geofencing-subscriptions.v0.area-left":
        print(f"Device left zone. Subscription: {subscription_id}")
    elif event_type == "org.camaraproject.geofencing-subscriptions.v0.subscription-ends":
        reason = data.get("terminationReason")  # documented field
        print(f"Subscription {subscription_id} ended. Reason: {reason}")

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    # Create subscriptions for all zones
    create_all_zone_subscriptions()

    # Example: list active subscriptions
    print(list_all_subscriptions())

    # Run the webhook receiver
    # NOTE: host/port/debug flags here are standard Flask usage,
    # not part of the geofencing API.
    app.run(host="0.0.0.0", port=5000)