"""
The two things a visitor needs to see, each on its own address.

They cannot both be true at once, which is the whole reason this file exists.

A service wired to Nokia proves the integration is real - and shows a
permanently calm city, because Nokia's test devices never move and no crowd can
form on them. A service wired to the simulated city shows a crowd forming and an
alarm firing eight minutes early - and talks to nobody.

Choosing one at deploy time leaves whoever opens the link looking at whichever
half they did not want. So both are offered:

    GET  /api/demo/nokia        four real calls to Nokia, and their real answers
    POST /api/demo/simulation   start a fresh crowd, visible on every screen
    GET  /api/demo/simulation   what is running
    DELETE /api/demo/simulation stop it and hand the screens back

Signing in is required but any account will do, including a citizen one. A judge
who signs up on the app can use both without being given an operator account.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import runtime
from app.auth.deps import current_user
from app.camara.client import Area

logger = logging.getLogger("crovia.demo")
router = APIRouter(prefix="/api/demo", tags=["demo"])

# Nokia's four test devices, and what their documentation says each should
# answer. Kept here so the endpoint can report not only what came back but
# whether it matched - including where it does not.
TEST_DEVICES = [
    ("+99999991000", "FALSE", "not in the area, SMS only"),
    ("+99999991001", "TRUE", "in the area, has data"),
    ("+99999991002", "PARTIAL", "partly in the area, SMS and data"),
    ("+99999991003", "UNKNOWN", "location unknown, unreachable"),
]

# The Lusail chokepoint the whole product is built around, so the question
# asked is the real one rather than an arbitrary circle.
LUSAIL_RAMP = Area(25.4240, 51.4904, 600)

# Real calls cost real money, and a page anyone can refresh would spend it on
# every visit. The answers are fixed anyway, so a few minutes of cache changes
# nothing about what is shown.
_CACHE_S = 300
_cache: dict | None = None
_cached_at: float = 0.0


class SimulationIn(BaseModel):
    """Optional shape of the crowd to simulate."""

    zone: str | None = None
    attendees: int | None = None
    release_minutes: float | None = None


@router.get("/nokia")
def nokia_check(refresh: bool = False, _: dict = Depends(current_user)):
    """
    Ask Nokia about its four test devices and report exactly what came back.

    No crowd is involved and none is possible: four devices cannot form one,
    and they never move. What this shows is that the calls are real, the key
    works, and the answers are Nokia's.
    """
    global _cache, _cached_at

    if _cache is not None and not refresh and (time.time() - _cached_at) < _CACHE_S:
        return {**_cache, "cached": True,
                "cached_seconds_ago": round(time.time() - _cached_at)}

    key = os.getenv("NOKIA_NAC_API_KEY", "").strip()
    if not key:
        return {
            "live": False,
            "reason": "NOKIA_NAC_API_KEY is not set on this service, so these "
                      "would be answered by a built-in stand-in rather than by "
                      "Nokia. Nothing is shown rather than something that looks "
                      "real and is not.",
        }

    from app.camara.client import NokiaClient

    client = NokiaClient(api_key=key)
    started = time.time()
    devices = []
    for phone, documented, description in TEST_DEVICES:
        row = {"device": phone, "description": description,
               "documented_answer": documented}
        t0 = time.time()
        try:
            r = client.verify_location(phone, LUSAIL_RAMP)
            row["answer"] = r["verification_result"]
            if "match_rate" in r:
                row["match_rate"] = r["match_rate"]
        except Exception as exc:
            row["answer"] = None
            row["error"] = f"{type(exc).__name__}: {exc}"[:160]
        row["took_ms"] = round((time.time() - t0) * 1000)
        row["matches_documentation"] = row.get("answer") == documented
        devices.append(row)

    # The one call that returns coordinates. Worth showing next to the others,
    # because it contradicts them: the same device reads as inside a circle in
    # Lusail and as standing in Budapest.
    position = {}
    try:
        position = client.retrieve_location("+99999991001")
    except Exception as exc:
        position = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"[:160]}

    mismatched = [d["device"] for d in devices if not d["matches_documentation"]]

    _cache = {
        "live": True,
        "question": "Is this device inside a 600 m circle at the Lusail north "
                    "concourse?",
        "area": {"lat": LUSAIL_RAMP.lat, "lon": LUSAIL_RAMP.lon,
                 "radius_m": LUSAIL_RAMP.radius_m},
        "devices": devices,
        "exact_position_of_1001": position,
        "calls_spent": client.ledger.summary()["total"],
        "took_ms": round((time.time() - started) * 1000),
        "notes": [
            "These are the only four devices Nokia provides. Any other number "
            "is refused, because in Simulator mode there is no real network "
            "behind it.",
            "Each answer is fixed to the number rather than worked out from a "
            "position: the same device answers the same way about a circle "
            "anywhere in the world.",
            "Location Retrieval places +99999991001 in Budapest while Location "
            "Verification reports it inside a circle in Lusail, 4,000 km away. "
            "Two APIs disagreeing about one device is the clearest proof the "
            "answers are invented rather than measured.",
        ],
        "cached": False,
    }
    if mismatched:
        _cache["notes"].append(
            f"{', '.join(mismatched)} did not match the documentation. The live "
            "simulator returns PARTIAL and UNKNOWN the other way round. This is "
            "Nokia's own inconsistency, not a fault in the reading.")
    _cached_at = time.time()
    return _cache


@router.get("/simulation")
def simulation_status(_: dict = Depends(current_user)):
    """What, if anything, is being simulated right now."""
    return runtime.demo_status()


@router.post("/simulation")
def start_simulation(body: SimulationIn | None = None,
                     user: dict = Depends(current_user)):
    """
    Start a fresh crowd, visible on every screen.

    Always from the beginning. The simulated event runs its course in a few
    minutes, so showing whatever state the server happens to be in is how a
    visitor arrives after the crowd has dispersed and concludes nothing works.

    While this is running, the map, the alarms and the warnings all come from
    the simulated city rather than from the real network - so it is deliberately
    easy to see, and easy to stop.
    """
    body = body or SimulationIn()
    if body.attendees is not None and not (100 <= body.attendees <= 200_000):
        raise HTTPException(status_code=422,
                            detail="attendees must be between 100 and 200,000")
    if body.release_minutes is not None and not (1 <= body.release_minutes <= 120):
        raise HTTPException(status_code=422,
                            detail="release_minutes must be between 1 and 120")
    if body.zone:
        from app.core.city import city
        if body.zone not in city.zones:
            raise HTTPException(status_code=422,
                                detail=f"unknown zone {body.zone}")

    status = runtime.start_demo(body.zone, body.attendees, body.release_minutes)
    logger.info("demonstration started by %s", user.get("username"))
    return {
        **status,
        "started_by": user.get("username"),
        "what_to_expect": [
            "A crowd builds at the chosen chokepoint over the next few minutes.",
            "The alarm fires before it becomes dangerous, not after.",
            "Every screen now shows the simulated city. Nothing here is real "
            "network data, and the service says so in its own logs.",
        ],
    }


@router.delete("/simulation")
def stop_simulation(user: dict = Depends(current_user)):
    """Stop simulating and hand every screen back to the real source."""
    out = runtime.stop_demo()
    logger.info("demonstration stopped by %s", user.get("username"))
    return out
