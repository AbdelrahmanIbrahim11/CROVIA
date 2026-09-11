"""
CROVIA backend.

Brings up three things that used to exist separately: the user database, the
detection engine, and the CAMARA notification endpoints. The engine previously
ran only inside the simulation, while the webhooks still called the earlier
services, so the running system was executing a design that had been replaced.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.api.state import router as state_router
from app.api.webhooks import router as webhook_router
from app.core.city import city
from app.db.redis import close_redis, get_redis
from app.runtime import engine_now, get_engine, step_twin
from app.services import (enrollment, incidents, operator_zones, priority,
                          warnings)
from app.usersDB.db import create_table, drop_username_uniqueness, getdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("crovia.main")

TICK_SECONDS = float(os.getenv("ENGINE_TICK_SECONDS", "30"))


async def _engine_loop() -> None:
    """
    Drive the engine on a fixed beat.

    Notifications arrive whenever the network sends them, but deciding what to
    spend has to happen on a rhythm of its own, otherwise a quiet city would
    never be reassessed and a busy one would be reassessed on every packet.
    """
    engine = get_engine()
    # In twin mode a demo is sped up, but the ENGINE must still see the world at
    # its normal cadence. Advancing thirty minutes of simulated time and then
    # ticking once means the engine takes two samples of a crowd that formed
    # entirely between them, and a fill it never saw cannot be detected. So the
    # world moves in ordinary-sized steps and the engine runs after each one;
    # only the wall-clock wait between them is shortened.
    step_s = float(os.getenv("ENGINE_STEP_SECONDS", "30"))
    while True:
        try:
            now = engine_now()
            if now is None:
                engine.tick()
            else:
                speed = float(os.getenv("CROVIA_TWIN_SPEED", "1"))
                for _ in range(max(1, int(TICK_SECONDS * speed / step_s))):
                    step_twin(step_s)
                    engine.tick(engine_now())
        except Exception:
            logger.exception("engine tick failed")
        await asyncio.sleep(TICK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("creating database tables")
    try:
        create_table()
        # Existing databases keep constraints that create_table() will not
        # change, and this one turned a second person with the same name into
        # a 500.
        drop_username_uniqueness()
    except Exception as exc:
        logger.error("database unavailable: %s", exc)

    engine = get_engine()

    # Rebuild who is being watched from the database. Without this the engine
    # comes back up monitoring nobody while still looking healthy.
    try:
        db = next(getdb())
        try:
            loaded = enrollment.load_into_registry(db, engine.registry)
            logger.info("restored %d sentinels and %d panel devices from the database",
                        loaded["sentinels"], loaded["panel"])
        finally:
            db.close()
    except Exception as exc:
        logger.warning("could not restore monitored devices: %s", exc)

    # Put the operator's own zones back. Redrawing them after every restart
    # would fall due during the event that made them worth drawing.
    try:
        db = next(getdb())
        try:
            n = operator_zones.load_all(db, city, engine)
            if n:
                logger.info("restored %d operator-drawn zones", n)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("could not restore operator zones: %s", exc)

    # Write every alarm down. The engine calls these; it never holds a session
    # itself, so a database problem can slow the record but not the detection.
    def _record_alarm(record: dict) -> None:
        db = next(getdb())
        try:
            row = incidents.open_incident(db, record)
            # Recording the alarm and telling people about it are one action.
            # Splitting them is how a system ends up with a complete incident
            # log and nobody warned.
            result = warnings.warn_people_near(db, engine.registry, record,
                                               incident_id=row.id)
            # Give the responders a connection that works.
            #
            # Done on the alarm rather than when somebody acknowledges it,
            # because acknowledging is itself an action taken in the app -
            # waiting for it would protect the connection only after it was
            # already needed.
            prio = priority.dispatch(db, engine.client, row.id,
                                     record.get("zone_id", ""))
            if prio.get("opened"):
                engine.log("priority",
                           f"{prio['opened']} responders given a protected "
                           f"connection ({prio['profile']})",
                           zone=record.get("zone_id"), **prio)
            engine.log("warned",
                       f"{result['sent']} people in {result.get('district_id', '?')} "
                       f"were warned about {record.get('segment_label')}",
                       zone=record.get("zone_id"), **result)
        finally:
            db.close()

    def _close_alarm(zone_id: str, _t: float) -> None:
        db = next(getdb())
        try:
            row = incidents.open_row_for(db, zone_id)
            incidents.close_incident(db, zone_id)
            # Hand the priority back. Sessions are billed while they live, and
            # an operator will withdraw a priority that never ends.
            if row is not None:
                priority.stand_down(db, engine.client, row.id)
        finally:
            db.close()

    engine.on_alert_raised = _record_alarm
    engine.on_alert_cleared = _close_alarm

    # A crash during an incident leaves paid priority sessions running with
    # nothing that remembers their ids.
    try:
        db = next(getdb())
        try:
            priority.close_orphans(db, engine.client)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("could not release old priority sessions: %s", exc)

    logger.info("city: %s, %d districts, %d zones",
                city.meta["label"], len(city.districts), len(city.zones))

    task = asyncio.create_task(_engine_loop())
    yield

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await close_redis()
    logger.info("crovia shutting down")


app = FastAPI(
    title="CROVIA",
    description="Crowd safety from telecom network signals",
    version="0.2.0",
    lifespan=lifespan,
)

# The Expo app runs from a different origin in development.
#
# "*" is fine locally and wrong in a deployment: it lets any website call this
# API with a visitor's browser. So a deployment must name its origins, and the
# service refuses to start rather than quietly allowing everyone.
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
if os.getenv("CROVIA_ENV", "local").lower() != "local" and _origins == ["*"]:
    raise RuntimeError(
        "CORS_ORIGINS must name the app's real address when CROVIA_ENV is not "
        "'local', for example https://crovia.example.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(auth_router)
app.include_router(state_router)


@app.get("/health")
async def health():
    engine = get_engine()
    try:
        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status": "ok",
        "redis": redis_ok,
        "city": city.meta["label"],
        "monitored": {
            "total": len(engine.registry.sentinels),
            "panel": engine.registry.panel_size(),
            "located": len(engine.registry.device_district),
        },
        "calls_spent": engine.ledger.total,
    }


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

