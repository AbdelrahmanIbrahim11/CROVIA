

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from crovia.config.redis_client import get_redis, close_redis
from crovia.trigger.subscription_manager import bootstrap_subscriptions
from crovia.webhook.handlers import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("crovia.main")

def _load_opted_in_devices() -> list[dict]:

    return [
        {"phone_number": "+201001234567", "tower_cell_id": "tower_cairo_nac_001"},
        {"phone_number": "+201001234568", "tower_cell_id": "tower_cairo_nac_001"},
        {"phone_number": "+201001234569", "tower_cell_id": "tower_cairo_nac_002"},
        {"phone_number": "+201001234570", "tower_cell_id": "tower_new_admin_001"},
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("creating Nokia NaC subscriptions")

    redis = await get_redis()
    devices = _load_opted_in_devices()

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