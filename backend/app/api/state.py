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

from app.core.city import city
from app.runtime import get_engine
from app.ai import graph as ai
from app.services import enrollment
from app.usersDB.db import getdb

router = APIRouter(prefix="/api", tags=["state"])


@router.get("/city")
def get_city():
    """Geography, so the app can draw without hard-coding coordinates."""
    return {
        "city": city.meta,
        "constants": city.constants,
        "districts": [
            {"id": d.id, "label": d.label, "short": d.short, "radius_m": d.radius_m,
             "lat": d.center.lat, "lon": d.center.lon}
            for d in city.districts.values()
        ],
        "zones": [
            {"id": z.id, "label": z.label, "district_id": z.district_id,
             "kind": z.kind, "radius_m": z.radius_m,
             "lat": z.center.lat, "lon": z.center.lon,
             "capacity_per_min": round(city.zone_capacity_per_min(z.id)),
             "bottleneck": (lambda b: {"id": b.id, "label": b.label,
                                       "width_m": b.width_m} if b else None)(
                 city.bottleneck_of(z.id)),
             }
            for z in city.zones.values()
        ],
        "segments": [
            {"id": s.id, "zone_id": s.zone_id, "label": s.label,
             "width_m": s.width_m, "risk": s.risk,
             "area_m2": round(s.area_m2),
             "capacity_per_min": round(s.capacity_per_min(city.capacity_per_m)),
             "path": [{"lat": p.lat, "lon": p.lon} for p in s.points]}
            for s in city.segments.values()
        ],
    }


@router.get("/state")
def get_state():
    """The live picture: zone verdicts, alerts, predictions and spend."""
    e = get_engine()
    snap = e.snapshot()
    return {
        **snap,
        "alerts": e.alerts[-20:],
        "predictions": e.predictions[-10:],
        "reasoning": [t for t in e.trace
                      if t["kind"] in ("alert", "predict", "prearm", "allocate",
                                       "unresolved", "suppress", "standdown")][-25:],
        "monitored": {
            "sentinels": len(e.registry.sentinels),
            "panel": e.registry.panel_size(),
            "located": len(e.registry.device_district),
        },
    }


@router.post("/agent/step")
def agent_step():
    """
    Run one decision cycle.

    The agent picks where to look and what to spend; the deterministic rules
    then judge whether anyone is in danger. Each result carries both, so the
    reasoning and the verdict can be read side by side.
    """
    return {"decisions": ai.run_once(get_engine())}


@router.get("/agent/policy")
def agent_policy():
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
def get_alerts():
    return {"alerts": get_engine().alerts}


class ConsentIn(BaseModel):
    phone_number: str
    scope: str = "safety_monitoring"


@router.post("/consent")
def post_consent(body: ConsentIn, db: Session = Depends(getdb)):
    row = enrollment.grant_consent(db, body.phone_number, body.scope)
    return {"hashed_id": row.hashed_id, "granted_at": row.granted_at, "scope": row.scope}


@router.delete("/consent")
def delete_consent(body: ConsentIn, db: Session = Depends(getdb)):
    """Withdraw permission. Monitoring stops in the same transaction."""
    if not enrollment.revoke_consent(db, body.phone_number):
        raise HTTPException(status_code=404, detail="no consent on file for that number")
    return {"status": "revoked"}


class EnrolIn(BaseModel):
    phone_number: str
    role: str = "sentinel"
    district_id: str | None = None


@router.post("/enrol")
def post_enrol(body: EnrolIn, db: Session = Depends(getdb)):
    dev = enrollment.enrol(db, body.phone_number, body.role, body.district_id)
    if dev is None:
        raise HTTPException(status_code=403,
                            detail="no active consent for that number - nothing is monitored "
                                   "without it")
    e = get_engine()
    if body.role == enrollment.PANEL:
        e.registry.add_panel(body.phone_number, body.district_id)
    else:
        e.registry.add_sentinel(body.phone_number, body.district_id)
    subs = enrollment.subscribe_device(db, e, body.phone_number, body.district_id)
    return {"hashed_id": dev.hashed_id, "role": dev.role,
            "district_id": dev.district_id, **subs}


@router.post("/enrol/auto")
def post_auto_enrol(db: Session = Depends(getdb)):
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
    return {"enrolled": out, "loaded_into_engine": loaded, "subscriptions_created": n_subs}
