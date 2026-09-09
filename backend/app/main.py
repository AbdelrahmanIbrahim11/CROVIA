import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Response

from app.db.redis import get_redis, close_redis
from app.services.subscription_manager import bootstrap_subscriptions
from app.api.webhooks import router as webhook_router
from app.services.location_retrieval import location_retrieval_listener
from app.usersDB.db import create_table, getdb
from app.usersDB.schemas import admin_user, normal_user, authority_user
from app.usersDB.dto import user_dto
from app.respones.responses import UserResponse
from sqlalchemy.orm import Session
from app.usersDB import services as dbServices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("crovia.main")


def _load_opted_in_devices() -> list[dict]:

    # Placeholder sentinel fleet for the Lusail pilot. `tower_cell_id` now holds
    # a district id from the shared geography file rather than a cell id — a
    # device is not bound to one tower for the life of its subscription, and
    # congestion notifications carry no location, so the district a reading gets
    # attributed to has to be tracked separately per device.
    return [
        {"phone_number": "+97430001001", "tower_cell_id": "district_stadium"},
        {"phone_number": "+97430001002", "tower_cell_id": "district_stadium"},
        {"phone_number": "+97430001003", "tower_cell_id": "district_foxhills"},
        {"phone_number": "+97430001004", "tower_cell_id": "district_central"},
        {"phone_number": "+97430001005", "tower_cell_id": "district_marina"},
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Initializing database tables...")

    try:
        create_table()
    except Exception as e:
        logger.error("Failed to initialize database: %s", e, exc_info=True)
        raise e

    logger.info("creating Nokia NaC subscriptions")

    redis = await get_redis()
    devices = _load_opted_in_devices()

    # Start the location retrieval Redis listener in the background
    listener_task = asyncio.create_task(location_retrieval_listener(redis))

    try:
        results = await bootstrap_subscriptions(redis, devices)
        logger.info(
            "Subscriptions created: %d congestion, %d geofencing, %d errors",
            len(results["congestion"]),
            len(results["geofencing"]),
            len(results["errors"]),
        )
        if results["errors"]:
            for err in results["errors"]:
                logger.error("Subscription error: %s", err)
    except Exception as e:
        logger.error("Failed to bootstrap subscriptions: %s", e, exc_info=True)

    yield

    logger.info("Cancelling background tasks...")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    await close_redis()
    logger.info("Crovia shutting down.")


app = FastAPI(
    title="Crovia — Dual-Trigger Pipeline",
    description="Webhook backend for Nokia NaC congestion + geofencing lead to Location Retrieval trigger",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)


@app.get("/health")
async def health():
    redis = await get_redis()
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {"status": "ok", "redis": redis_ok}


@app.post("/signin", response_model=UserResponse)
def signin(user_Data: user_dto, db: Session = Depends(getdb)):
    user = None
    if not dbServices.signin_existing_mail(db=db, email=user_Data.email):
        if user_Data.user_type == "normal":
            normaluser = {
                "username": {user_Data.username},
                "password": {user_Data.password},
                "email": {user_Data.email},
                "number": {user_Data.number},
            }
            user = dbServices.create_user(
                db=db, userdata=normaluser, user_role="normal"
            )
        elif user_Data.user_type == "admin":
            adminuser = {
                "username": {user_Data.username},
                "password": {user_Data.password},
                "email": {user_Data.email},
            }
            user = dbServices.create_user(db=db, userdata=adminuser, user_role="admin")
        elif user_Data.user_type == "authority":
            authorityuser = {
                "username": {user_Data.username},
                "password": {user_Data.password},
                "email": {user_Data.email},
            }
            user = dbServices.create_user(
                db=db, userdata=authorityuser, user_role="admin"
            )

        if user:
            return UserResponse(
                username=str(user.username),
                email=str(user.email),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="An error occured!"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The email already exists!"
        )


@app.get("/login", response_model=UserResponse)
def login(user_Data: user_dto, db: Session = Depends(getdb)):
    if dbServices.verify_user(
        db=db, userdata=user_Data.model_dump(), user_role=user_Data.user_type
    ):
        return Response(
            content=UserResponse(username=user_Data.username, email=user_Data.email),
            status_code=200,
        )
    else:
        return Response(content=None, status_code=status.HTTP_404_NOT_FOUND)
