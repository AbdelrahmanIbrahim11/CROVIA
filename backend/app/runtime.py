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


# Set when the engine is running against the twin, so a demo cannot be mistaken
# for live network data.
twin_mode: bool = False
_twin = None

# A demonstration run, started on request and independent of how the service
# booted.
#
# It exists because the two things a visitor needs to see cannot both be true
# at once: a service wired to Nokia proves the integration and shows a
# permanently calm city, because Nokia's test devices never move; a service
# wired to the simulated city shows a crowd and talks to nobody. Rather than
# choose at deploy time and leave a judge looking at whichever half they did
# not want, either can be asked for.
#
# While a demonstration is running it replaces what every screen reads, so the
# map, the alarms and the warnings are all the simulated city's - and stopping
# it hands everything back.
_demo_engine: Engine | None = None
_demo_twin = None
_demo_started_at: float | None = None
_demo_source: str = "twin"

# How much faster simulated time runs than real time, during a demonstration.
#
# Twelve rather than one because a demonstration is watched by a person
# standing there. Measured end to end: at real speed the crowd takes about
# eight minutes to become dangerous, which is long enough that most people
# decide it is broken and stop looking. At twelve the alarm arrives after
# thirty seconds, the all-clear after two minutes, and the crowd has gone by
# five - fast enough to hold attention, and still slow enough to watch the
# queue BUILD, which is the entire point. Faster was tried: at twenty the
# alarm fires at twelve seconds, before anyone has finished reading the
# screen, and it reads as a jump rather than something forming.
#
# It affects nothing outside a demonstration - the live service has no
# simulated clock to accelerate - and it is a default in code rather than a
# dashboard setting so that a deployment cannot silently lose it.
DEMO_SPEED_DEFAULT = "12"
_scenario: dict | None = None

# How an engine gets wired to the rest of the system: saving alarms, warning
# people, giving responders priority. Registered once at startup and applied to
# every engine built afterwards.
#
# Without this a demonstration produced alarms that appeared on the map and
# nothing else - no incident written, nobody warned - because the hooks had
# been attached to the engine the service booted with and never moved.
_install_hooks = None


def set_hook_installer(fn) -> None:
    global _install_hooks
    _install_hooks = fn


def build_engine() -> Engine:
    """
    Create the engine and choose what is underneath it.

    Three options, in order of preference:

      NOKIA         a real API key is set. Live network.
      TWIN          CROVIA_TWIN=1. A simulated Lusail with people who actually
                    move, behind the same CAMARA interface. This exists because
                    Nokia's sandbox cannot move a device, so it is the only way
                    to see a crowd form end to end.
      SIMULATOR     the default. Answers from Nokia's published test numbers.

    The simulator is the default rather than an error, because the system should
    come up and be inspectable without credentials.
    """
    global twin_mode, _twin
    api_key = os.getenv("NOKIA_NAC_API_KEY", "").strip()
    budget = Budget(per_hour=int(os.getenv("BUDGET_PER_HOUR", "6000")))

    if api_key:
        logger.info("CAMARA: live Nokia Network as Code")
        return Engine(city, NokiaClient(api_key=api_key), DeviceRegistry(), budget)

    if os.getenv("CROVIA_TWIN", "").strip() in ("1", "true", "yes"):
        engine = _build_twin_engine(budget)
        twin_mode = True
        logger.warning("CAMARA: TWIN MODE - simulated crowds, not real network data")
        return engine

    logger.info("CAMARA: simulator (no NOKIA_NAC_API_KEY set)")
    return Engine(city, SimulatorClient(), DeviceRegistry(), budget)


def _build_twin_engine(budget: Budget) -> Engine:
    """Wire a moving population behind the CAMARA interface."""
    global _twin
    import numpy as np

    from app.camara.client import Area, ApiError
    from app.detect.engine import ScheduledEvent
    from sim.camara_twin import TwinCamaraClient
    from sim.twin import Event, Population, Twin

    zone = os.getenv("CROVIA_TWIN_ZONE", "zone_stadium_north_concourse")
    attendees = int(os.getenv("CROVIA_TWIN_ATTENDEES", "12000"))
    minutes = float(os.getenv("CROVIA_TWIN_MINUTES", "12"))

    _twin = Twin(city, Population(), [Event(zone, attendees, duration_s=minutes * 60,
                                            label="scheduled event")])
    client = TwinCamaraClient(_twin)
    registry = DeviceRegistry()
    engine = Engine(city, client, registry, budget)
    engine.add_scheduled(ScheduledEvent(zone, 0.0, attendees, duration_s=minutes * 60,
                                        label="scheduled event"))

    rng = np.random.default_rng(3)
    app_idx = np.where(_twin.has_app)[0]
    by_district: dict[str, list[int]] = {d: [] for d in city.districts}
    for i in app_idx:
        by_district[_twin.home_district[i]].append(int(i))

    def phone(i: int) -> str:
        return f"+974{30000000 + i}"

    for did, members in by_district.items():
        rng.shuffle(members)
        for i in members[:60]:
            p = phone(i)
            client.bind(p, i)
            h = registry.add_sentinel(p)
            try:
                sub = client.create_congestion_subscription(p, "twin", 86400)
                registry.bind_subscription(sub, h, "congestion", did)
                # A geofence on EVERY district, exactly as subscribe_device does
                # for the real network.
                #
                # With one subscription per device - on the district it started
                # in - a simulated person who walked out was removed from that
                # fleet and never added to the one they walked into, because
                # they had no subscription there. Over a few minutes every fleet
                # drained, no district held enough devices to be trusted, and a
                # crowd formed with nothing watching it.
                for other, d in city.districts.items():
                    g, evt = client.create_geofence_subscription(
                        p, other, Area(d.center.lat, d.center.lon, d.radius_m),
                        "twin", 86400, True)
                    registry.bind_subscription(g, h, "district", other)
                    if evt and evt["type"] == "area-entered":
                        registry.place(h, other, 0.0)
            except ApiError:
                pass
    for i in rng.choice(app_idx, size=400, replace=False):
        p = phone(int(i))
        client.bind(p, int(i))
        registry.add_panel(p, _twin.home_district[int(i)])
    return engine


def _build_scenario_engine(budget: Budget, key: str = "egress") -> Engine:
    """
    Wire the honest scenario behind the CAMARA interface.

    The alternative to the twin, and the one to show a visitor. The twin gives
    every person the same chance of carrying the app, which makes the counting
    panel a perfect sample and the headcount unbiased by construction - the most
    flattering assumption in the project. This world makes app ownership vary
    almost five-fold between districts, so the panel genuinely misrepresents the
    city, and it also assumes the planned population figure is a little wrong.

    Nothing here uses `width * 72`. Movement is limited by space and by walking
    speed falling as the ground fills, so the ramp's throughput is a consequence
    rather than a restatement of the detector's own rule.

    People exist only in memory. No accounts are created and nothing is written
    to the database, exactly as with the twin - a real person who has signed up
    is warned alongside the simulated ones because their location is unknown,
    which is the rule that covers anyone newly enrolled.
    """
    global _scenario
    import numpy as np

    from app.camara.client import Area
    from scenario.catalogue import BY_KEY, CATALOGUE
    from scenario.network import ScenarioNetwork
    from scenario.webhook import Delivery
    from scenario.world import World

    spec = BY_KEY.get(key) or CATALOGUE[0]
    world = World(spec)
    registry = DeviceRegistry()

    # The engine reads its ledger from the client at construction, so the
    # network has to exist first. Delivery needs the engine, which does not
    # exist yet, so it is attached a moment later - the notification path is
    # not used until the first step, well after both are built.
    delivery = Delivery()
    net = ScenarioNetwork(world, delivery, spec=spec)
    engine = Engine(city, net, registry, budget)
    delivery.engine = engine

    rng = np.random.default_rng(5)
    app_idx = np.where(world.has_app)[0]
    panel_n = int(os.getenv("CROVIA_SCENARIO_PANEL", "400"))
    sentinel_n = int(os.getenv("CROVIA_SCENARIO_SENTINELS", "800"))

    chosen = rng.choice(app_idx, size=min(panel_n + sentinel_n, app_idx.size),
                        replace=False)
    for k, i in enumerate(chosen):
        phone = f"+9745{int(i):07d}"
        net.bind(phone, int(i))
        if k < panel_n:
            registry.add_panel(phone)
        else:
            h = registry.add_sentinel(phone)
            sub = net.create_congestion_subscription(phone, "scenario", 86400)
            registry.bind_subscription(sub, h, "congestion", "")
            # A geofence on every district, as production does. The network
            # answers for the one the device is really in and says nothing
            # about the rest, so it places itself.
            for did, d in city.districts.items():
                g, _ = net.create_geofence_subscription(
                    phone, did, Area(d.center.lat, d.center.lon, d.radius_m),
                    "scenario", 86400, True)
                registry.bind_subscription(g, h, "district", did)

    _scenario = {"world": world, "net": net, "clock": 0.0,
                 "phase_i": 0, "phase_t": 0.0, "spec": spec}
    return engine


def step_scenario(seconds: float) -> None:
    """
    Advance the scenario world and let the network push what it would push.

    Walks the phase schedule - calm, arrival, match, egress, dispersal - so a
    visitor sees an ordinary evening turn dangerous and then recover, rather
    than a crowd that is simply there when they arrive.
    """
    if _scenario is None:
        return
    sc = _scenario
    SCHEDULE = sc["spec"].schedule
    sc["clock"] += seconds
    sc["phase_t"] += seconds

    phase = SCHEDULE[min(sc["phase_i"], len(SCHEDULE) - 1)]
    if sc["phase_t"] >= phase.minutes * 60 and sc["phase_i"] < len(SCHEDULE) - 1:
        sc["phase_i"] += 1
        sc["phase_t"] = 0.0
        phase = SCHEDULE[sc["phase_i"]]
        logger.info("scenario phase: %s - %s", phase.name, phase.note)

    sc["world"].step(seconds, phase.name)
    sc["net"].push_notifications(sc["clock"])


def scenario_phase() -> dict | None:
    """Which part of the evening is being shown, for the demo screen."""
    if _scenario is None:
        return None
    spec = _scenario["spec"]
    p = spec.schedule[min(_scenario["phase_i"], len(spec.schedule) - 1)]
    return {"scenario": spec.key, "title": spec.title,
            "name": p.name, "note": p.note,
            "minute": round(_scenario["clock"] / 60.0, 1),
            "phases": [x.name for x in spec.schedule],
            "should_an_alarm_fire": spec.should_fire,
            "what_to_expect": spec.expected}


def _active_twin():
    """The twin the loop should advance: the demonstration's, or the booted one."""
    return _demo_twin if _demo_twin is not None else _twin


def step_twin(seconds: float) -> None:
    """
    Advance the simulated world and deliver its notifications.

    CROVIA_TWIN_SPEED multiplies simulated time. A stadium crowd takes about
    fifteen minutes to build, so at real time a demo is fifteen minutes of
    watching almost nothing. The engine is unaffected: it still sees events in
    the order and spacing the twin produces.
    """
    if _scenario is not None:
        step_scenario(seconds)
        return
    twin = _active_twin()
    if twin is None:
        return
    engine = get_engine()
    steps = max(1, int(seconds / twin.dt))
    for _ in range(steps):
        twin.step()
    engine.now = twin.t
    for ev in engine.client.tick(twin.t):
        if ev["type"] == "congestion":
            engine.on_congestion(ev["subscriptionId"], ev["congestionLevel"],
                                 ev["confidenceLevel"])
        else:
            engine.on_geofence(ev["subscriptionId"], ev["type"])


def engine_now() -> float | None:
    """
    The clock the engine should use.

    In twin mode this is simulated time, which starts at zero. Letting tick()
    fall back to wall-clock time mixed the two: step_twin set the engine's clock
    to the twin's time and tick() immediately replaced it with a Unix timestamp,
    so every cadence comparison measured a gap of decades and no zone was ever
    due to be counted.
    """
    if _scenario is not None:
        return _scenario["clock"]
    twin = _active_twin()
    return None if twin is None else twin.t


def twin_truth() -> dict | None:
    """Ground truth, for the demo view only. The engine never reads this."""
    _t = _active_twin()
    if _t is None:
        return None
    snap = _t.history[-1] if _t.history else None
    zones = {}
    for z in city.zones:
        # A zone an operator drew after the twin was built has no simulated
        # truth to compare against. That is expected, not an error: the twin
        # models the city plan, and the operator is watching something the plan
        # does not contain. Reported as null so the demo view can say "no
        # ground truth" instead of the whole endpoint failing.
        if snap is None or z not in snap.get("zones", {}):
            zones[z] = {"true_people": None, "true_density": None,
                        "simulated": False}
            continue
        zones[z] = {"true_people": _t.people_in_zone(z),
                    "true_density": round(snap["zones"][z]["worst_density"], 2),
                    "simulated": True}
    return {"t": _twin.t, "zones": zones}


def get_engine() -> Engine:
    """
    The engine every screen reads.

    A running demonstration takes precedence, so nothing downstream has to know
    a demonstration exists - the map, the warnings and the incident list all
    follow automatically.
    """
    global _engine
    if _demo_engine is not None:
        return _demo_engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def demo_running() -> bool:
    return _demo_engine is not None


def start_demo(zone: str | None = None, attendees: int | None = None,
               minutes: float | None = None, source: str = "twin",
               scenario: str = "egress") -> dict:
    """
    Begin a fresh simulated event.

    Always fresh. Showing whatever state the server happened to be in is how a
    visitor arrives after the crowd has dispersed and concludes that nothing
    works, so every request starts the story from the beginning.
    """
    global _demo_engine, _demo_twin, _demo_started_at
    import time as _time

    stop_demo()
    if zone:
        os.environ["CROVIA_TWIN_ZONE"] = zone
    if attendees:
        os.environ["CROVIA_TWIN_ATTENDEES"] = str(attendees)
    if minutes:
        os.environ["CROVIA_TWIN_MINUTES"] = str(minutes)

    global _demo_source
    _demo_source = source
    budget = Budget(per_hour=int(os.getenv("BUDGET_PER_HOUR", "6000")))
    if source == "scenario":
        # The default. An ordinary evening that turns dangerous, on a world
        # built to remove the assumptions that flattered the twin.
        _demo_engine = _build_scenario_engine(budget, scenario)
        _demo_twin = None
    else:
        _demo_engine = _build_twin_engine(budget)
        _demo_twin = _twin
    if _install_hooks is not None:
        _install_hooks(_demo_engine)
    _demo_started_at = _time.time()
    logger.warning("demonstration started - simulated crowds, not real network data")
    return demo_status()


def stop_demo() -> dict:
    """Hand every screen back to the real engine."""
    global _demo_engine, _demo_twin, _demo_started_at, _scenario
    was = _demo_engine is not None
    _demo_engine = None
    _demo_twin = None
    _scenario = None
    _demo_started_at = None
    if was:
        logger.info("demonstration stopped - back to the live network")
    return {"running": False, "stopped": was}


def demo_status() -> dict:
    import time as _time

    if _demo_engine is None:
        return {"running": False,
                "note": "nothing is simulated; the service is using its real source"}
    if _demo_source == "scenario":
        ph = scenario_phase() or {}
        return {
            "running": True,
            "source": "scenario",
            "scenario": ph.get("scenario"),
            "title": ph.get("title"),
            "should_an_alarm_fire": ph.get("should_an_alarm_fire"),
            "phase": ph.get("name"),
            "what_is_happening": ph.get("note"),
            "phases": ph.get("phases"),
            "simulated_minute": ph.get("minute"),
            "real_seconds": round(_time.time() - _demo_started_at, 1)
            if _demo_started_at else 0,
            "speed": float(os.getenv("CROVIA_TWIN_SPEED", DEMO_SPEED_DEFAULT)),
            "alerts": len(_demo_engine.alerts),
        }
    z = os.getenv("CROVIA_TWIN_ZONE", "zone_stadium_north_concourse")
    return {
        "running": True,
        "source": "twin",
        "zone": z,
        "attendees": int(os.getenv("CROVIA_TWIN_ATTENDEES", "12000")),
        "release_minutes": float(os.getenv("CROVIA_TWIN_MINUTES", "12")),
        "simulated_seconds": round(_demo_twin.t, 1) if _demo_twin else 0,
        "real_seconds": round(_time.time() - _demo_started_at, 1) if _demo_started_at else 0,
        "speed": float(os.getenv("CROVIA_TWIN_SPEED", DEMO_SPEED_DEFAULT)),
        "alerts": len(_demo_engine.alerts),
    }


def reset_engine() -> None:
    global _engine
    _engine = None
