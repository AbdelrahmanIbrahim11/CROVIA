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

from app.api.state import router as state_router
from app.api.webhooks import router as webhook_router
from app.core.city import city
from app.db.redis import close_redis, get_redis
from app.respones.responses import UserResponse
from app.runtime import engine_now, get_engine, step_twin
from app.services import enrollment, incidents
from app.usersDB import services as dbServices
from app.usersDB.db import create_table, getdb
from app.usersDB.dto import user_dto

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

    # Write every alarm down. The engine calls these; it never holds a session
    # itself, so a database problem can slow the record but not the detection.
    def _record_alarm(record: dict) -> None:
        db = next(getdb())
        try:
            incidents.open_incident(db, record)
        finally:
            db.close()

    def _close_alarm(zone_id: str, _t: float) -> None:
        db = next(getdb())
        try:
            incidents.close_incident(db, zone_id)
        finally:
            db.close()

    engine.on_alert_raised = _record_alarm
    engine.on_alert_cleared = _close_alarm

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
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

@app.post("/signin", response_model=UserResponse)
def signin(user_Data: user_dto, db: Session = Depends(getdb)):
    if dbServices.signin_existing_mail(db=db, email=user_Data.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The email already exists!")

    fields = {"username": user_Data.username, "password": user_Data.password,
              "email": user_Data.email}
    if user_Data.user_type == "normal":
        fields["number"] = user_Data.number
    role = "normal" if user_Data.user_type == "normal" else "admin"
    user = dbServices.create_user(db=db, userdata=fields, user_role=role)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An error occured!")

    return UserResponse(username=str(user.username), email=str(user.email))


@app.get("/login", response_model=UserResponse)
def login(user_Data: user_dto, db: Session = Depends(getdb)):
    if not dbServices.verify_user(db=db, userdata=user_Data.model_dump(),
                                  user_role=user_Data.user_type):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return UserResponse(username=user_Data.username, email=user_Data.email)
