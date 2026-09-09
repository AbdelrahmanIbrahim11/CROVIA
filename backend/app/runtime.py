"""
The single live detection engine the whole process shares.

FastAPI handlers, the webhook receivers and the background loop all need the
same engine instance. Building one per request would give each request its own
empty history and no crowd would ever be detected.
"""

from __future__ import annotations

import logging
import os

from app.camara.client import NokiaClient, SimulatorClient
from app.core.budget import Budget
from app.core.city import city
from app.core.registry import DeviceRegistry
from app.detect.engine import Engine

logger = logging.getLogger("crovia.runtime")

_engine: Engine | None = None


def build_engine() -> Engine:
    """
    Create the engine, choosing a real or simulated network.

    With no API key configured the simulator is used, which answers from Nokia's
    published test numbers. That is a deliberate default: the system should come
    up and be inspectable without credentials, rather than failing at import.
    """
    api_key = os.getenv("NOKIA_NAC_API_KEY", "").strip()
    if api_key:
        client = NokiaClient(api_key=api_key)
        logger.info("CAMARA: live Nokia Network as Code")
    else:
        client = SimulatorClient()
        logger.info("CAMARA: simulator (no NOKIA_NAC_API_KEY set)")

    budget = Budget(per_hour=int(os.getenv("BUDGET_PER_HOUR", "6000")))
    return Engine(city, client, DeviceRegistry(), budget)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None
