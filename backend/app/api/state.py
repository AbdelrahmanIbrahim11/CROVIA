"""
What the app reads.

One endpoint carries the whole live picture, because the map needs districts,
zones, alerts and spend together and consistently — several endpoints would let
the map draw one moment's zones beside another moment's alerts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import current_user, phone_of, require_authority, require_operator
from app.core.registry import hash_phone
from app.core.city import city
from app import runtime
from app.runtime import get_engine
from app.ai import graph as ai
from app.services import enrollment, incidents, operator_zones, push, warnings
from app.usersDB.db import getdb

router = APIRouter(prefix="/api", tags=["state"])


@router.get("/city")
def get_city():
    """Geography, so the app can draw without hard-coding coordinates."""
    return {
        "city": city.meta,
        "constants": city.constants,
        "districts": [
            {
                "id": d.id,
                "label": d.label,
                "short": d.short,
                "radius_m": d.radius_m,
                "lat": d.center.lat,
                "lon": d.center.lon,
            }
            for d in city.districts.values()
        ],
        "zones": [
            {
                "id": z.id,
                "label": z.label,
                "district_id": z.district_id,
                "kind": z.kind,
                "radius_m": z.radius_m,
                "lat": z.center.lat,
                "lon": z.center.lon,
                "capacity_per_min": round(city.zone_capacity_per_min(z.id)),
                "bottleneck": (
                    lambda b: (
                        {"id": b.id, "label": b.label, "width_m": b.width_m}
                        if b
                        else None
                    )
                )(city.bottleneck_of(z.id)),
            }
            for z in city.zones.values()
        ],
        "segments": [
            {
                "id": s.id,
                "zone_id": s.zone_id,
                "label": s.label,
                "width_m": s.width_m,
                "risk": s.risk,
                "area_m2": round(s.area_m2),
                "capacity_per_min": round(s.capacity_per_min(city.capacity_per_m)),
                "path": [{"lat": p.lat, "lon": p.lon} for p in s.points],
            }
            for s in city.segments.values()
        ],
    }


@router.get("/state")
def get_state(_: dict = Depends(require_operator)):
    """
    The live picture: zone verdicts, alerts, predictions and spend.

    Operators only. This was briefly opened to any signed-in account while
    fixing the citizen screen, which had been polling it and getting 403. That
    made the fix work and handed every citizen the headcounts, the API spend,
    the panel size and the simulation ground truth.

    The citizen screen reads /api/nearby instead, which carries the severities
    and that person's own warnings and nothing else.
    """
    e = get_engine()
    snap = e.snapshot()
    return {
        **snap,
        "alerts": e.alerts[-20:],
        "predictions": e.predictions[-10:],
        "reasoning": [
            t
            for t in e.trace
            if t["kind"]
            in (
                "alert",
                "predict",
                "prearm",
                "allocate",
                "unresolved",
                "suppress",
                "standdown",
            )
        ][-25:],
        "monitored": {
            "sentinels": len(e.registry.sentinels),
            "panel": e.registry.panel_size(),
            "located": len(e.registry.device_district),
        },
        # Labelled clearly: a demo must never be mistaken for network data.
        "twin_mode": runtime.twin_mode,
        "ground_truth": runtime.twin_truth(),
    }


@router.post("/agent/step")
def agent_step(_: dict = Depends(require_operator)):
    """
    Run one decision cycle.

    The agent picks where to look and what to spend; the deterministic rules
    then judge whether anyone is in danger. Each result carries both, so the
    reasoning and the verdict can be read side by side.
    """
    e = get_engine()
    now = runtime.engine_now()
    if now is not None:
        e.now = now
    return {"decisions": ai.run_once(e)}


@router.get("/agent/policy")
def agent_policy(_: dict = Depends(require_operator)):
    e = get_engine()
    policy = getattr(e, "_policy", None) or ai.build_policy()
    e._policy = policy
    return {
        "policy": policy.name,
        "explanation": (
            "A model chooses where to look and what to spend. Whether people are in "
            "danger is always decided by deterministic rules, so an alarm can be "
            "audited afterwards."
        ),
        "tools": ai.T.TOOL_SPECS,
    }


@router.get("/alerts")
def get_alerts(_: dict = Depends(require_operator)):
    return {"alerts": get_engine().alerts}


class ConsentIn(BaseModel):
    phone_number: str
    scope: str = "safety_monitoring"


@router.get("/incidents")
def get_incidents(
    limit: int = 50, db: Session = Depends(getdb), _: dict = Depends(require_operator)
):
    """
    Alarms that have been recorded, newest first.

    /alerts is what is happening now and lives in memory. This is the history,
    and it survives a restart — which is what makes baselines from real days
    possible later.
    """
    return {"incidents": incidents.history(db, limit=limit)}


class IncidentActionIn(BaseModel):
    """What the responder did. Free text, because the real answer varies."""

    action_taken: str | None = None


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: str,
    db: Session = Depends(getdb),
    user: dict = Depends(require_authority),
):
    """
    Say that a named person has seen this alarm and is dealing with it.

    Authority only. This is a record of responsibility, so it has to carry a
    real name - which is why it takes the name from the token rather than from
    the request body, where the caller could type anything.
    """
    row = incidents.acknowledge(db, incident_id, who=user.get("username", "unknown"))
    if row is None:
        raise HTTPException(status_code=404, detail="no such incident")
    return row


@router.post("/incidents/{incident_id}/close")
def close_incident(
    incident_id: str,
    body: IncidentActionIn,
    db: Session = Depends(getdb),
    user: dict = Depends(require_authority),
):
    """
    Close an incident because somebody dealt with it, and record what they did.

    Different from the engine closing a zone when the crowd leaves. "It cleared
    on its own" and "we opened two more gates" are different lessons for the
    next event, so both are kept.
    """
    row = incidents.close_by_hand(
        db,
        incident_id,
        who=user.get("username", "unknown"),
        action_taken=body.action_taken,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no such incident")
    return row


@router.get("/nearby")
def get_nearby(db: Session = Depends(getdb), user: dict = Depends(current_user)):
    """
    What a person in the city is allowed to see.

    The citizen screen used to poll /api/state, which is operations data and is
    refused to a citizen with 403 - so the screen sat on "offline" forever and
    showed nothing useful no matter what was happening outside.

    This carries the same picture at the resolution a member of the public
    needs: which places are busy, and anything addressed to them. It leaves out
    what is nobody's business - headcounts, API spend, the panel size, the
    ground truth - so a citizen account cannot be used to survey the city.
    """
    engine = get_engine()
    snap = engine.snapshot()

    zones = {}
    for zid, v in snap["zones"].items():
        if not v:
            zones[zid] = None
            continue
        # Severity only, and the name of the hazard. No numbers of people.
        zones[zid] = {
            "zone_id": zid,
            "dangerous": v["dangerous"],
            "severity": v["severity"],
            "segment_label": v["segment_label"],
            "band_label": v["band_label"],
        }

    phone = phone_of(db, user)
    mine = warnings.inbox(db, hash_phone(phone), limit=5) if phone else []

    return {
        "t": snap["t"],
        "zones": zones,
        "districts": snap["districts"],
        # Only what is live now, and only the words - not the headcount.
        "alerts": [{"zone_id": a["zone_id"], "segment_label": a["segment_label"],
                    "reason": a["reason"], "t": a["t"]}
                   for a in engine.alerts[-3:]],
        "my_warnings": mine,
        # Named apart from /api/state's "monitored", which is the operations
        # count of sentinels and panel devices. Here it means one thing about
        # one person: is CROVIA watching for YOU. Two endpoints using the same
        # word for different things is how a citizen screen ends up showing an
        # operations figure by accident.
        "you_are_monitored": bool(phone),
    }


class PushTokenIn(BaseModel):
    """The address a phone's operating system gave the app."""

    token: str
    platform: str | None = None


@router.post("/push/register")
def register_push(body: PushTokenIn, db: Session = Depends(getdb),
                  user: dict = Depends(current_user)):
    """
    Remember where this person's phone can be reached.

    Stored against their hash, worked out from their own account - the caller
    cannot register a device on somebody else's behalf.

    Only a citizen account has a phone to warn. An operator watches the city;
    they are not the ones being told to avoid it.
    """
    phone = phone_of(db, user)
    if not phone:
        raise HTTPException(status_code=400,
                            detail="only a citizen account receives warnings")
    row = push.register(db, hash_phone(phone), body.token.strip(), body.platform)
    return {"registered": True, "platform": row.platform}


@router.delete("/push/register")
def unregister_push(body: PushTokenIn, db: Session = Depends(getdb),
                    _: dict = Depends(current_user)):
    """Forget a device, when a person signs out or turns warnings off."""
    return {"removed": push.unregister(db, body.token.strip())}


@router.get("/push/coverage")
def push_coverage(db: Session = Depends(getdb),
                  _: dict = Depends(require_operator)):
    """
    How many people can actually be reached on a phone.

    An operator needs this next to the warning count: "we warned 400 people"
    means something different when only 12 of them have the app installed.
    """
    return push.coverage(db)


@router.get("/warnings/me")
def my_warnings(db: Session = Depends(getdb), user: dict = Depends(current_user)):
    """
    The warnings sent to the person calling.

    The caller cannot name whose warnings they want. The hash is derived from
    their own account, so there is no id to guess and no way to read somebody
    else's. That matters: a warning says where a named person was standing.
    """
    phone = phone_of(db, user)
    if not phone:
        return {"warnings": [], "note": "only citizen accounts receive warnings"}
    return {"warnings": warnings.inbox(db, hash_phone(phone))}


@router.get("/warnings/{hashed_id}")
def get_warnings(
    hashed_id: str, db: Session = Depends(getdb), _: dict = Depends(require_operator)
):
    """Any person's warnings, for operations. Addressed by hash, never by number."""
    return {"warnings": warnings.inbox(db, hashed_id)}


@router.post("/warnings/{delivery_id}/read")
def read_warning(
    delivery_id: str, db: Session = Depends(getdb), user: dict = Depends(current_user)
):
    """Mark one warning as seen. A citizen may only mark their own."""
    owner = None
    if user.get("role") == "normal":
        phone = phone_of(db, user)
        if not phone:
            raise HTTPException(status_code=404, detail="no such warning")
        owner = hash_phone(phone)
    if not warnings.mark_read(db, delivery_id, owner_hash=owner):
        raise HTTPException(status_code=404, detail="no such warning")
    return {"status": "read"}


@router.get("/warnings/coverage/{zone_id}")
def warning_coverage(
    zone_id: str, db: Session = Depends(getdb), _: dict = Depends(require_operator)
):
    """
    How many people were reached about this zone, against how many are monitored
    at all. An operator needs the second number to read the first one honestly.
    """
    return warnings.coverage(db, zone_id, registry=get_engine().registry)


class OperatorZoneIn(BaseModel):
    """
    A zone an operator drew on the map.

    width_m and length_m are required rather than optional. The danger rule
    starts from the narrowest link, so a circle without one cannot be judged,
    and guessing a width would produce a capacity figure with nothing behind it.
    """

    label: str
    district_id: str
    lat: float
    lon: float
    radius_m: float
    width_m: float
    length_m: float
    risk: float = 1.3
    created_by: str | None = None


@router.get("/zones/operator")
def list_operator_zones(
    db: Session = Depends(getdb), _: dict = Depends(require_operator)
):
    return {"zones": operator_zones.listing(db)}


@router.post("/zones/operator")
def add_operator_zone(
    body: OperatorZoneIn,
    db: Session = Depends(getdb),
    user: dict = Depends(require_operator),
):
    """
    Watch a place the city plan does not know about: a gate open only tonight,
    a temporary barrier, the exit the away supporters are being sent to.

    Judged by exactly the same rules as every other zone.
    """
    try:
        return operator_zones.create(
            db,
            city,
            get_engine(),
            label=body.label,
            district_id=body.district_id,
            lat=body.lat,
            lon=body.lon,
            radius_m=body.radius_m,
            width_m=body.width_m,
            length_m=body.length_m,
            risk=body.risk,
            created_by=user.get("username"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/zones/operator/{zone_id}")
def delete_operator_zone(
    zone_id: str, db: Session = Depends(getdb), _: dict = Depends(require_operator)
):
    if not operator_zones.remove(db, city, get_engine(), zone_id):
        raise HTTPException(
            status_code=404,
            detail="no drawn zone with that id - zones from the "
            "city plan cannot be deleted",
        )
    return {"status": "removed"}


def _own_number_or_operator(db: Session, user: dict, phone_number: str) -> None:
    """
    A citizen may only grant or withdraw consent for their own number.

    Without this check anyone signed in could withdraw a stranger's consent and
    switch off the monitoring that protects them, or enrol a number that never
    agreed to anything.
    """
    if user.get("role") != "normal":
        return
    own = phone_of(db, user)
    if own != phone_number:
        raise HTTPException(
            status_code=403, detail="you can only change consent for your own number"
        )


@router.get("/consent/me")
def my_consent(db: Session = Depends(getdb), user: dict = Depends(current_user)):
    """
    Whether CROVIA is watching the person calling, and since when.

    A person is entitled to know this about themselves without asking anybody,
    which is why it is a plain endpoint on their own account rather than
    something only operations can look up.
    """
    from app.usersDB.models import device_consent

    phone = phone_of(db, user)
    if not phone:
        return {"monitored": False, "note": "only citizen accounts are ever monitored"}
    row = (
        db.query(device_consent)
        .filter(device_consent.phone_number == phone)
        .one_or_none()
    )
    if row is None:
        return {"monitored": False, "phone_number": phone}
    return {
        "monitored": row.revoked_at is None,
        "phone_number": phone,
        "hashed_id": row.hashed_id,
        "granted_at": row.granted_at.isoformat() if row.granted_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "scope": row.scope,
    }


@router.post("/consent")
def post_consent(
    body: ConsentIn, db: Session = Depends(getdb), user: dict = Depends(current_user)
):
    _own_number_or_operator(db, user, body.phone_number)
    row = enrollment.grant_consent(db, body.phone_number, body.scope)
    return {
        "hashed_id": row.hashed_id,
        "granted_at": row.granted_at,
        "scope": row.scope,
    }


@router.delete("/consent")
def delete_consent(
    body: ConsentIn, db: Session = Depends(getdb), user: dict = Depends(current_user)
):
    """Withdraw permission. Monitoring stops in the same transaction."""
    _own_number_or_operator(db, user, body.phone_number)
    if not enrollment.revoke_consent(db, body.phone_number):
        raise HTTPException(
            status_code=404, detail="no consent on file for that number"
        )
    return {"status": "revoked"}


class EnrolIn(BaseModel):
    phone_number: str
    role: str = "sentinel"
    district_id: str | None = None


@router.post("/enrol")
def post_enrol(
    body: EnrolIn, db: Session = Depends(getdb), _: dict = Depends(require_operator)
):
    dev = enrollment.enrol(db, body.phone_number, body.role, body.district_id)
    if dev is None:
        raise HTTPException(
            status_code=403,
            detail="no active consent for that number - nothing is monitored "
            "without it",
        )
    e = get_engine()
    if body.role == enrollment.PANEL:
        e.registry.add_panel(body.phone_number, body.district_id)
    else:
        e.registry.add_sentinel(body.phone_number, body.district_id)
    subs = enrollment.subscribe_device(db, e, body.phone_number, body.district_id)
    return {
        "hashed_id": dev.hashed_id,
        "role": dev.role,
        "district_id": dev.district_id,
        **subs,
    }


@router.post("/enrol/auto")
def post_auto_enrol(db: Session = Depends(getdb), _: dict = Depends(require_operator)):
    """Build the fleet and the panel from everyone who has consented."""
    e = get_engine()
    out = enrollment.auto_enrol_users(db, districts=list(city.districts))
    loaded = enrollment.load_into_registry(db, e.registry)
    # Subscribe everything that is now monitored, so notifications can actually
    # be attributed to a device and a district.
    n_subs = 0
    for hashed, phone in list(e.registry.vault._to_phone.items()):
        district = e.registry.district_of(hashed)
        r = enrollment.subscribe_device(db, e, phone, district)
        n_subs += len(r.get("subscriptions", []))
    return {
        "enrolled": out,
        "loaded_into_engine": loaded,
        "subscriptions_created": n_subs,
    }
