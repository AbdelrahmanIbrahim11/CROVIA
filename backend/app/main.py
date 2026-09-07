

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.redis import get_redis, close_redis
from app.services.subscription_manager import bootstrap_subscriptions
from app.api.webhooks import router as webhook_router
from app.services.location_retrieval import location_retrieval_listener

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