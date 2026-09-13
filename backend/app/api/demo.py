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
from app.auth.deps import current_user, optional_user
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

    # Which world to run.
    #
    # "twin" is the default because it is what the published detection figures
    # were measured on and what the deployed demonstration has always shown.
    # "scenario" plays one of the harder evenings in scenario/catalogue.py -
    # a fairer test, and still being calibrated, so it is opt-in rather than
    # something a visitor gets by surprise.
    source: str = "twin"
    # Which evening to play when source is "scenario".
    # See GET /api/demo/scenarios for the list.
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


# ---------------------------------------------------------------------------
# Every API, on the four devices Nokia gives us
# ---------------------------------------------------------------------------

# What each API is charged at, so the page can show the cost of what it just
# did rather than asserting a price list. Mirrors core/budget.py.
_API_ORDER = [
    ("location_verification", "Location Verification", 1.0,
     "Is this device inside this circle? The main sensor - every headcount "
     "comes from this call. Returns no coordinates."),
    ("reachability", "Device Status - Reachability", 0.5,
     "Can this device answer at all? A free pre-filter, so we never pay to "
     "locate a handset that is switched off."),
    ("location_retrieval", "Location Retrieval", 3.0,
     "Actual coordinates. Bought once, at the moment an alarm fires, for about "
     "twenty devices - never for routine counting."),
    ("qod", "Quality on Demand", 5.0,
     "Asks the network to protect a responder's connection. The only API here "
     "that CHANGES the network rather than reporting on it."),
    ("congestion_insights", "Congestion Insights", 1.0,
     "Subscribes a device so the network pushes us a notification when its "
     "cell is busy. Free to listen; this is what decides where to look."),
    ("geofencing", "Geofencing", 1.0,
     "Subscribes a device to a district boundary so the network tells us which "
     "district it is really in. This is what gives congestion an address."),
]

# A QoD session is created REQUESTED and becomes AVAILABLE only once the
# network has actually allocated resources, which took about fifteen seconds
# when measured. Every session is created first and read afterwards, so one
# wait covers all four rather than four waits covering one each.
_QOD_WAIT_S = float(os.getenv("DEMO_QOD_WAIT_SECONDS", "16"))
# Long enough to read the status back, short enough that a session forgotten by
# a crash expires on its own. Deleted explicitly either way.
_QOD_DURATION_S = 120

_apis_cache: dict | None = None
_apis_cached_at: float = 0.0


def _timed(fn, *args, **kwargs) -> dict:
    """Run one call and report what came back, including the failure."""
    t0 = time.time()
    try:
        value = fn(*args, **kwargs)
        return {"ok": True, "answer": value,
                "took_ms": round((time.time() - t0) * 1000)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200],
                "took_ms": round((time.time() - t0) * 1000)}


@router.get("/apis")
def all_apis(refresh: bool = False, skip_qod: bool = False,
             user: dict | None = Depends(optional_user)):
    """
    Call every CAMARA API CROVIA uses, on Nokia's four test devices, and report
    the raw answers.

    READABLE WITHOUT AN ACCOUNT, WHICH IS THE POINT. Somebody sent this link
    will paste it into a browser, and a browser address bar cannot carry a
    bearer token - so an endpoint whose entire purpose is to let a stranger
    check that the integration is real must not begin by refusing them. There
    is nothing here to protect: the only devices involved are Nokia's four
    fixed test numbers, which belong to nobody and never move.

    What signing in buys is the right to SPEND. The answer is cached, and only
    a signed-in caller may force a fresh run, because that costs real calls and
    an open refresh button is an open invitation to empty the budget.

    WHY THIS EXISTS. /api/demo/nokia proves two of the six APIs: it verifies
    four locations and retrieves one position. Somebody checking whether this
    project really talks to Nokia had no way to see the other four, and a
    claim that an API is "wired up" is worth nothing next to its live answer.

    So this calls all six, in front of the reader, and prints what came back.
    Including the answers that are wrong: two of Nokia's four devices contradict
    their own documentation, and Location Verification and Location Retrieval
    disagree about where device 1001 is by roughly four thousand kilometres.
    Those are reported rather than quietly dropped, because a page that only
    shows the calls that worked is not evidence of anything.

    SUBSCRIPTIONS ARE CREATED AND THEN DELETED. Congestion and geofencing are
    push APIs: the only way to prove they work is to open a subscription. Each
    one is torn down in the same request, and given a short expiry as well, so
    a failure here cannot leave paid subscriptions running for ever.

    QoD IS THE SLOW ONE. A session is created REQUESTED and only becomes
    AVAILABLE once the network has allocated resources, which takes about
    fifteen seconds. All four are opened first and read afterwards, so the wait
    happens once. Pass skip_qod=true to skip it if you only want the fast calls.

    The whole result is cached for five minutes: the answers are fixed to the
    device anyway, and a page anyone can refresh should not spend real money on
    every visit.
    """
    global _apis_cache, _apis_cached_at

    # Refreshing spends money, so it is the one thing that needs an account.
    # Silently ignored rather than refused: a visitor who adds ?refresh=true
    # out of curiosity should still get the page.
    if refresh and user is None:
        refresh = False

    if _apis_cache is not None and not refresh and (time.time() - _apis_cached_at) < _CACHE_S:
        return {**_apis_cache, "cached": True,
                "cached_seconds_ago": round(time.time() - _apis_cached_at)}

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
    from app.config import settings
    from app.core.city import city

    client = NokiaClient(api_key=key)
    started = time.time()
    results: dict[str, dict] = {}
    phones = [p for p, _d, _desc in TEST_DEVICES]

    # --- 1. Location Verification -----------------------------------------
    rows = []
    for phone, documented, description in TEST_DEVICES:
        r = _timed(client.verify_location, phone, LUSAIL_RAMP)
        row = {"device": phone, "description": description,
               "documented_answer": documented, "took_ms": r["took_ms"]}
        if r["ok"]:
            row["answer"] = r["answer"]["verification_result"]
            if "match_rate" in r["answer"]:
                row["match_rate"] = r["answer"]["match_rate"]
            row["matches_documentation"] = row["answer"] == documented
        else:
            row["error"] = r["error"]
            row["matches_documentation"] = False
        rows.append(row)
    results["location_verification"] = {
        "question": "Is this device inside a 600 m circle at the Lusail north "
                    "concourse?",
        "area": {"lat": LUSAIL_RAMP.lat, "lon": LUSAIL_RAMP.lon,
                 "radius_m": LUSAIL_RAMP.radius_m},
        "devices": rows,
    }

    # --- 2. Reachability ---------------------------------------------------
    rows = []
    for phone, _documented, description in TEST_DEVICES:
        r = _timed(client.get_reachability, phone)
        row = {"device": phone, "description": description,
               "took_ms": r["took_ms"]}
        row.update(r["answer"] if r["ok"] else {"error": r["error"]})
        rows.append(row)
    results["reachability"] = {
        "question": "Can this device be reached, and over what?",
        "devices": rows,
    }

    # --- 3. Location Retrieval --------------------------------------------
    rows = []
    for phone, _documented, description in TEST_DEVICES:
        r = _timed(client.retrieve_location, phone, 120)
        row = {"device": phone, "description": description,
               "took_ms": r["took_ms"]}
        row.update(r["answer"] if r["ok"] else {"error": r["error"]})
        rows.append(row)
    results["location_retrieval"] = {
        "question": "Where is this device, in coordinates?",
        "devices": rows,
        "note": "Compare 1001 with its Location Verification answer above. "
                "Verification puts it inside a circle in Lusail; retrieval puts "
                "it in Budapest. Two APIs cannot both be right about one "
                "handset, which is the clearest evidence these answers are "
                "fixed to the phone number rather than measured.",
    }

    # --- 4. Quality on Demand ---------------------------------------------
    if skip_qod:
        results["qod"] = {"skipped": True,
                          "note": "skip_qod=true was passed, so no session was "
                                  "opened. Drop the parameter to run it."}
    else:
        server_ip = os.getenv("QOD_APP_SERVER_IP", "").strip()
        if not server_ip:
            results["qod"] = {
                "skipped": True,
                "note": "QOD_APP_SERVER_IP is not set on this service. QoD "
                        "prioritises the route between a device and ONE named "
                        "server, so without an address there is nothing to "
                        "prioritise towards and no honest call to make.",
            }
        else:
            profile = os.getenv("QOD_PROFILE", "QOS_E").strip() or "QOS_E"
            opened: list[dict] = []
            for phone, _documented, description in TEST_DEVICES:
                r = _timed(client.create_qod_session, phone, server_ip,
                           profile, _QOD_DURATION_S)
                row = {"device": phone, "description": description,
                       "profile": profile, "created_ms": r["took_ms"]}
                if r["ok"]:
                    row["session_id"] = r["answer"]["session_id"]
                    row["status_at_creation"] = r["answer"]["status"]
                else:
                    row["error"] = r["error"]
                opened.append(row)

            # One wait for all four, not four waits for one each.
            live = [r for r in opened if r.get("session_id")]
            if live:
                time.sleep(_QOD_WAIT_S)
            for row in live:
                back = _timed(client.get_qod_session, row["session_id"])
                if back["ok"]:
                    row["status_after_wait"] = back["answer"]["status"]
                    row["status_info"] = back["answer"].get("status_info")
                else:
                    row["read_error"] = back["error"]
                # Always torn down. A session is billed for as long as it
                # lives, so a demonstration that leaves four of them running is
                # a demonstration of how to waste money.
                gone = _timed(client.delete_qod_session, row["session_id"])
                row["deleted"] = gone["ok"]
                if not gone["ok"]:
                    row["delete_error"] = gone["error"]

            became_available = sum(1 for r in opened
                                   if r.get("status_after_wait") == "AVAILABLE")
            results["qod"] = {
                "question": f"Will the network protect this device's route to "
                            f"{server_ip} using {profile}?",
                "waited_seconds": _QOD_WAIT_S if live else 0,
                "reached_available": f"{became_available}/{len(opened)}",
                "devices": opened,
                "note": "A session is created REQUESTED and becomes AVAILABLE "
                        "only once the network has actually allocated "
                        "resources, so the status at creation proves nothing. "
                        "Every session above was deleted again in this same "
                        "request - sessions are billed while they live.",
            }

    # --- 5 and 6. The two push APIs ---------------------------------------
    # These have no question-and-answer form: the network pushes to us later.
    # What can be proved now is that a subscription is accepted, which is the
    # step everything else depends on. Each is deleted immediately.
    sink_base = settings.webhook_base_url.rstrip("/")
    token_set = bool(settings.webhook_auth_token
                     and settings.webhook_auth_token != "change-me")

    rows = []
    for phone, _documented, description in TEST_DEVICES:
        sink = f"{sink_base}/webhooks/congestion/{phone.lstrip('+')}"
        r = _timed(client.create_congestion_subscription, phone, sink, 300)
        row = {"device": phone, "description": description,
               "webhook": sink, "took_ms": r["took_ms"]}
        if r["ok"]:
            row["subscription_id"] = r["answer"]
            row["deleted"] = _timed(client.delete_subscription, r["answer"])["ok"]
        else:
            row["error"] = r["error"]
        rows.append(row)
    results["congestion_insights"] = {
        "question": "Will the network notify us when this device's cell is busy?",
        "devices": rows,
        "note": "A congestion notification carries only a level and a time "
                "window - no device identity and no location - so each device "
                "is subscribed at its own webhook address and that address is "
                "the only thing that identifies it. Every subscription above "
                "was deleted again in this same request.",
        "webhook_token_configured": token_set,
    }

    district = next(iter(city.districts.values()), None)
    rows = []
    if district is None:
        results["geofencing"] = {"skipped": True,
                                 "note": "no district is loaded in the city map"}
    else:
        area = Area(district.center.lat, district.center.lon, district.radius_m)
        for phone, _documented, description in TEST_DEVICES:
            sink = f"{sink_base}/webhooks/geofencing/{phone.lstrip('+')}"
            r = _timed(client.create_geofence_subscription, phone,
                       district.id, area, sink, 300)
            row = {"device": phone, "description": description,
                   "district": district.id, "webhook": sink,
                   "took_ms": r["took_ms"]}
            if r["ok"]:
                sub_id, initial = r["answer"]
                row["subscription_id"] = sub_id
                row["initial_event"] = initial
                row["deleted"] = _timed(client.delete_subscription, sub_id)["ok"]
            else:
                row["error"] = r["error"]
            rows.append(row)
        results["geofencing"] = {
            "question": f"Will the network tell us when this device enters or "
                        f"leaves {district.id}?",
            "area": {"lat": area.lat, "lon": area.lon, "radius_m": area.radius_m},
            "devices": rows,
            "note": "Geofences are placed at DISTRICT level on purpose. "
                    "Positioning is accurate to 150-400 m, so a tighter circle "
                    "would report a device entering and leaving constantly as "
                    "it moves between towers. Every subscription above was "
                    "deleted again in this same request.",
            "webhook_token_configured": token_set,
        }

    # --- what it cost, and whether each API answered ----------------------
    summary = []
    for api_key, label, weight, purpose in _API_ORDER:
        block = results.get(api_key, {})
        if block.get("skipped"):
            state, detail = "skipped", block.get("note", "")
        else:
            devices = block.get("devices", [])
            answered = sum(1 for d in devices if "error" not in d)
            state = ("live" if answered == len(devices) and devices
                     else "partial" if answered else "failed")
            detail = f"{answered}/{len(devices)} devices answered"
        summary.append({"api": label, "state": state, "detail": detail,
                        "relative_cost": weight, "what_it_is_for": purpose})

    _apis_cache = {
        "live": True,
        "devices_used": phones,
        "summary": summary,
        "results": results,
        "calls_spent": client.ledger.summary(),
        "took_ms": round((time.time() - started) * 1000),
        "notes": [
            "These are the only four devices Nokia provides in Simulator mode. "
            "Any other number is refused, because there is no real network "
            "behind it.",
            "Every answer is fixed to the phone number rather than worked out "
            "from a position, so the same device answers the same way about a "
            "circle anywhere in the world. That is why CROVIA's detection "
            "figures come from simulation: this proves the integration, and it "
            "cannot prove anything about a crowd.",
            "Nothing here was left running. Every subscription and every "
            "priority session created above was deleted in the same request.",
        ],
        "cached": False,
    }
    _apis_cached_at = time.time()
    return _apis_cache
