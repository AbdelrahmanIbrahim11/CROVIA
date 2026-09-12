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
    """
    Optional shape of what to simulate.

    `source` chooses the world. "scenario" is the default and the one to show a
    visitor: an ordinary evening that turns dangerous, on a city built to remove
    the assumptions that flattered the earlier tests - app ownership varies
    almost five-fold between districts, and the planned population figure is
    deliberately a little wrong.

    "twin" keeps the older, faster world available, which is still what the
    published detection figures were measured on.
    """

    source: str = "scenario"
    # Which evening to play. See GET /api/demo/scenarios for the list.
    scenario: str = "egress"
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


@router.get("/scenarios")
def list_scenarios(_: dict = Depends(current_user)):
    """
    The evenings a visitor can choose from, in plain language.

    Deliberately includes evenings where an alarm would be WRONG. A list made
    only of disasters would prove nothing about the thing that actually decides
    whether an operator keeps the system switched on, which is how often it
    cries wolf on an ordinary night.
    """
    from scenario.catalogue import listing

    items = listing()
    return {
        "scenarios": items,
        "how_to_run": "POST /api/demo/simulation with {\"scenario\": \"<key>\"}",
        "note": (
            f"{sum(1 for i in items if i['should_an_alarm_fire'])} of "
            f"{len(items)} should raise an alarm. The rest must stay silent - "
            "those are the harder tests."
        ),
        "honesty": [
            "App ownership varies almost five-fold between districts, so the "
            "counting panel genuinely misrepresents the city.",
            "CROVIA multiplies by the city plan's 30,000 while only about "
            "27,600 people are present, so its denominator is wrong.",
            "Nothing in the simulated world uses width x 72, the detector's "
            "own formula - the ramp's throughput emerges from space and "
            "walking speed instead.",
            "23% of location answers come back UNKNOWN, positioning carries a "
            "fixed per-cell bias, and 1.5% of calls fail outright.",
        ],
    }


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
    if body.source not in ("scenario", "twin"):
        raise HTTPException(status_code=422,
                            detail="source must be 'scenario' or 'twin'")
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

    if body.source == "scenario":
        from scenario.catalogue import BY_KEY
        if body.scenario not in BY_KEY:
            raise HTTPException(
                status_code=422,
                detail=f"unknown scenario {body.scenario!r} - see "
                       f"GET /api/demo/scenarios for the list")

    status = runtime.start_demo(body.zone, body.attendees, body.release_minutes,
                                source=body.source, scenario=body.scenario)
    logger.info("demonstration started by %s (%s)",
                user.get("username"), body.source)

    if body.source == "scenario":
        from scenario.catalogue import BY_KEY
        spec = BY_KEY[body.scenario]
        expect = [f"{p.name.upper()} ({p.minutes:.0f} min) - {p.note}"
                  for p in spec.schedule]
        expect.append(f"EXPECTED RESULT: {spec.expected}")
    elif False:
        expect = [
            "CALM - an ordinary evening. Nothing should happen, and almost no "
            "money is spent.",
            "ARRIVAL - 18,000 people travel to the stadium and go inside. The "
            "district fills; the exit ramp does not. Still no alarm.",
            "MATCH - everyone is seated and packed. Cell towers are saturated "
            "and congestion reads High across the district. This is the hardest "
            "false-alarm test in the scenario, and nothing should fire.",
            "EGRESS - full time. The crowd funnels into a 9 m ramp, the alarm "
            "fires, and a warning arrives on your phone.",
            "DISPERSAL - the zone clears, the alarm stands down, and an "
            "all-clear reaches everyone who was warned.",
        ]
    else:
        expect = [
            "A crowd builds at the chosen chokepoint over the next few minutes.",
            "The alarm fires before it becomes dangerous, not after.",
        ]

    return {
        **status,
        "started_by": user.get("username"),
        "what_to_expect": expect,
        "note": "Every screen now shows the simulated city. Nothing here is "
                "real network data, and the service says so in its own logs.",
    }


@router.delete("/simulation")
def stop_simulation(user: dict = Depends(current_user)):
    """Stop simulating and hand every screen back to the real source."""
    out = runtime.stop_demo()
    logger.info("demonstration stopped by %s", user.get("username"))
    return out
