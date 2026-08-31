"""
Example: Using the Network as Code (Nokia) Quality on Demand (QoD) API
to create, extend, monitor, and delete a prioritized network session.

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


def create_qod_session(
    device_phone_number: str,
    service_ip: str,
    qos_profile: str = "QOS_E",  # documented: stable latency under congestion
    duration_seconds: int = 3600,
):
    """
    Creates a QoD session prioritizing the connection between a device
    and a service, with an optional notification webhook.
    """
    session = client.qod.create_session_v1(
        application_server={
            "ipv_4_address": service_ip,  # documented; ipv_6_address is the
                                           # alternative if no IPv4 is used
        },
        qos_profile=qos_profile,  # documented: e.g. QOS_E, QOS_S, QOS_M, QOS_L
        device={
            "phone_number": device_phone_number,  # documented
            "ipv_4_address": {
                "publicAddress": service_ip,       # documented
                "privateAddress": "192.0.2.25",    # documented example value
                "publicPort": 80,                  # documented
            },
            # ipv_6_address is also documented as an optional device field
            # "ipv_6_address": "2001:db8:1234:5678:9abc:def0:fedc:ba98",
        },
        duration=duration_seconds,  # documented, optional, max 86400 (24h)

        # --- Optional: notification webhook (documented) ---
        sink="https://your-backend.com/webhooks/qod",
        sink_credential={
            "access_token": "some-access-token",       # documented
            "access_token_expires_utc": datetime.now(timezone.utc) + timedelta(days=1),  # documented
            "access_token_type": "bearer",              # documented, must be "bearer"
            # NOTE: docs also mention "credential_type" must be "ACCESSTOKEN",
            # but it's unclear from the example whether this key must be
            # explicitly included in the dict or is implied — included here
            # for completeness based on the parameters table.
            "credential_type": "ACCESSTOKEN",
        },
    )
    print(f"Session created: {session}")
    return session


def create_qod_session_with_ports(
    device_phone_number: str,
    service_ip: str,
    qos_profile: str = "QOS_L",
    duration_seconds: int = 3600,
):
    """
    Creates a QoD session restricted to specific ports on both the
    device and application server side (documented, optional feature).
    """
    session = client.qod.create_session_v1(
        device={"phone_number": device_phone_number},
        application_server={"ipv_4_address": service_ip},
        qos_profile=qos_profile,
        device_ports={"ranges": [{"from": 80, "to": 443}]},          # documented
        application_server_ports={"ports": [80, 443]},               # documented
        duration=duration_seconds,
    )
    return session


def extend_qod_session(session_id: str, additional_seconds: int = 300):
    """Extends an existing session's duration (documented method)."""
    response = client.qod.extend_session_v1(
        session_id=session_id,                               # documented
        requested_additional_duration=additional_seconds,     # documented
    )
    print(f"Session extended: {response}")
    return response


def get_all_sessions_for_device(device_phone_number: str):
    """Retrieves all QoD sessions associated with a device (documented method)."""
    return client.qod.retrieve_sessions_v1(
        device={"phone_number": device_phone_number}
    )


def get_session_by_id(session_id: str):
    """Retrieves a single QoD session by its ID (documented method)."""
    return client.qod.get_session_v1(session_id=session_id)


def delete_qod_session(session_id: str):
    """
    Deletes a QoD session. The docs explicitly recommend doing this
    once the session is no longer needed to avoid unexpected costs.
    """
    response = client.qod.delete_session_v1(session_id=session_id)
    print(f"Session deleted: {response}")
    return response


def wait_for_session_available(session_id: str, poll_interval_sec: int = 2, timeout_sec: int = 30):
    """
    Polls a session's status until it becomes AVAILABLE, fails, or times out.

    NOTE: The documentation states a session starts as REQUESTED and may
    become AVAILABLE or UNAVAILABLE, but does NOT specify a recommended
    polling interval or timeout — these values are a reasonable custom
    default, not documented guidance.
    """
    import time

    elapsed = 0
    while elapsed < timeout_sec:
        session = get_session_by_id(session_id)
        status = session.status  # documented field: REQUESTED / AVAILABLE / UNAVAILABLE

        if status == "AVAILABLE":
            print("Session is now available.")
            return session
        elif status == "UNAVAILABLE":
            print("Session became unavailable before it was ever available.")
            return session

        time.sleep(poll_interval_sec)
        elapsed += poll_interval_sec

    print("Timed out waiting for session to become available.")
    return None


# --- Example: handling an incoming QoD notification webhook ---
# The documentation's own example uses FastAPI.
from fastapi import FastAPI, Header
from pydantic import BaseModel
from typing_extensions import Annotated
from typing import Union

app = FastAPI()


class EventDetail(BaseModel):
    sessionId: str
    qosStatus: str
    statusInfo: str


class Event(BaseModel):
    eventType: str
    eventTime: str
    eventDetail: EventDetail


class Notification(BaseModel):
    id: str
    source: str
    type: str
    specversion: str
    datacontenttype: str
    time: str
    # NOTE: The docs show two slightly different shapes for this payload:
    # a plain JSON schema with only `data`, and this Pydantic model
    # example with both `event` and `data`. Both are included here to
    # match the documented handler example exactly, but this
    # inconsistency should be verified against the live API response.
    event: Event
    data: EventDetail


@app.post("/webhooks/qod")
def receive_qod_notification(
    notification: Notification,
    authorization: Annotated[Union[str, None], Header] = None,
):
    # Documented: auth expected as "Bearer <token>"
    if authorization == "Bearer my-token":
        print(f"QoD status changed: {notification.data.qosStatus} "
              f"(reason: {notification.data.statusInfo})")
        # TODO: trigger your crowd-safety logic here, e.g. retry or
        # fall back if the session became UNAVAILABLE unexpectedly
    else:
        # NOTE: docs don't specify expected behavior on auth failure
        print("Unauthorized QoD notification received — ignoring.")


if __name__ == "__main__":
    # Step 1: create a session for a first-responder device
    session = create_qod_session(
        device_phone_number="+99999991001",
        service_ip="233.252.0.2",
        qos_profile="QOS_E",
        duration_seconds=3600,
    )

    # Step 2: wait until the network confirms the session is active
    wait_for_session_available(session.session_id)

    # Step 3: extend the session if the incident is taking longer
    extend_qod_session(session.session_id, additional_seconds=300)

    # Step 4: list all sessions for this device
    print(get_all_sessions_for_device("+99999991001"))

    # Step 5: clean up when done
    delete_qod_session(session.session_id)

    # Run the webhook receiver
    # NOTE: uvicorn usage here is standard, not part of the QoD API itself.
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)