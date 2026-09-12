"""
A stand-in for Nokia that behaves the way Nokia documents, not the way we wish.

This is the ONLY route between the city in world.py and CROVIA. The engine can
never read a position, a headcount, or anything else directly - it can only ask
the questions the CAMARA APIs answer, and it receives the answers Nokia would
give, including the ones that are useless.

WHY THIS FILE EXISTS AT ALL
---------------------------
Nokia's sandbox has four phone numbers that never move. You cannot form a crowd
on four stationary devices, so the detection logic cannot be tested against the
real service - not because the integration is unfinished, but because there is
nothing there to detect. This stands in for the network so the LOGIC can be
tested, while app/camara/client.py remains the thing that talks to Nokia.

WHAT IS FAITHFUL TO THE DOCUMENTATION
-------------------------------------
CONGESTION carries no device id and no location. Its `data` field is a LIST of
recent time windows, newest first, and its `source` is the event type rather
than a URL - both of which are real quirks found by receiving live
notifications, and both of which make the message unattributable on its own.
The only thing identifying the device is the webhook address it arrives at.

GEOFENCING reports `area-entered` only, because that is the single event type
CROVIA subscribes to. A device that is NOT inside produces silence, never a
"no". Silence is ambiguous - it could equally be a lost message - and the
system has to cope with that rather than reading it as an answer.

LOCATION VERIFICATION returns TRUE, FALSE, PARTIAL or UNKNOWN. UNKNOWN is
common, and it means the network could not tell - NOT that the person is
somewhere else.

THE ERRORS ARE THE POINT
------------------------
Positioning carries a random error AND a per-cell systematic bias, so it is
wrong in a consistent direction in a given place rather than averaging out
neatly. A fixed share of answers come back UNKNOWN. A small share of calls fail
outright with 500/502/503/504. None of this is decoration: a detector that only
works on clean data is a detector that does not work.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np

from app.camara.client import Area, ApiError
from app.core.budget import (Ledger, TIER_CONGESTION_SUB, TIER_DELETE,
                             TIER_GEOFENCE_SUB, TIER_QOD, TIER_REACHABILITY,
                             TIER_RETRIEVE, TIER_VERIFY)

# ===========================================================================
# TUNABLES - how badly the network behaves
# ===========================================================================

# Share of Location Verification answers that come back UNKNOWN. Measured at
# about 23% against the live Nokia service.
UNKNOWN_PROB = 0.23

# Positioning error. `RANDOM` is fresh noise on every fix; `CELL_BIAS` is a
# fixed offset per part of the city, so error does not politely average away.
RANDOM_ERROR_M = 180.0
CELL_BIAS_M = 220.0

# Share of calls that fail outright.
TRANSIENT_ERROR_PROB = 0.015

# Congestion. A cell reports a level from how full it is relative to normal.
# Confidence is what CROVIA filters on - anything under 50 is discarded.
CONGESTION_LEVELS = [
    (3.0, "High"),
    (1.8, "Medium"),
    (1.1, "Low"),
    (0.0, "None"),
]
CONFIDENCE_RANGE = (55, 95)

# How often the network pushes a congestion update per device, in seconds.
# The documentation's samples run from about 90 s to 5 minutes.
CONGESTION_INTERVAL_S = 180.0

SEED = 23


class ScenarioNetwork:
    """
    Implements the same interface as NokiaClient, backed by world.py.

    `deliver` is the other half: it is what makes the network push notifications
    at CROVIA rather than waiting to be asked.
    """

    def __init__(self, world, webhook, ledger: Ledger | None = None,
                 spec=None) -> None:
        self.world = world
        # Per-scenario knobs. How often the network cannot answer, and how much
        # congestion is caused by things that are not crowds.
        self.spec = spec if spec is not None else getattr(world, "spec", None)
        self.unknown_prob = getattr(self.spec, "unknown_prob", UNKNOWN_PROB)
        self.congestion_noise = getattr(self.spec, "congestion_noise", 0.0)
        self.webhook = webhook            # scenario.webhook.Delivery
        self.ledger = ledger or Ledger()
        self.rng = np.random.default_rng(SEED)

        self.phone_to_index: dict[str, int] = {}
        self.subs: dict[str, dict] = {}
        self._seq = 0
        self._last_congestion: dict[str, float] = {}
        self._pending_initial: list[tuple] = []
        # What an ordinary evening looks like in this city, measured rather
        # than assumed. Congestion is reported RELATIVE to this, so "High"
        # means busy for Lusail rather than busy by some invented absolute.
        self.baseline_density = self._measure_calm_baseline()

        # A fixed positioning bias per square of the city, so the same place is
        # always wrong in the same direction.
        self._bias: dict[tuple[int, int], tuple[float, float]] = {}

    # ---- wiring --------------------------------------------------------

    def bind(self, phone: str, index: int) -> None:
        """Tie a phone number to a person in the world."""
        self.phone_to_index[phone] = index

    def _measure_calm_baseline(self) -> float:
        """
        Average local density across the city while nothing unusual is going on.

        Calibrating against this was necessary: a fixed reference made an
        ordinary evening read Medium everywhere, so every district looked
        equally busy, the comparison against the calmest one collapsed, and the
        system would have spent its whole budget on a city where nothing was
        happening.
        """
        n = min(200, self.world.n)
        idx = self.rng.choice(self.world.n, size=n, replace=False)
        vals = [self.world.local_density(int(i)) for i in idx]
        return max(float(np.mean(vals)), 1e-9)

    def _fail_sometimes(self) -> None:
        if self.rng.random() < TRANSIENT_ERROR_PROB:
            status = int(self.rng.choice([500, 502, 503, 504]))
            self.ledger.record_error(status)
            raise ApiError(status, "transient network error")

    def _bias_for(self, x: float, y: float) -> tuple[float, float]:
        key = (int(x // 800), int(y // 800))
        if key not in self._bias:
            ang = self.rng.uniform(0, 2 * math.pi)
            mag = abs(self.rng.normal(CELL_BIAS_M, CELL_BIAS_M * 0.3))
            self._bias[key] = (math.cos(ang) * mag, math.sin(ang) * mag)
        return self._bias[key]

    def _observed_position(self, i: int) -> tuple[float, float]:
        """Where the network THINKS someone is. Never where they are."""
        tx, ty = self.world.x[i], self.world.y[i]
        bx, by = self._bias_for(tx, ty)
        return (tx + bx + self.rng.normal(0, RANDOM_ERROR_M),
                ty + by + self.rng.normal(0, RANDOM_ERROR_M))

    def _area_xy(self, area: Area) -> tuple[float, float]:
        return self.world._to_xy(area.lat, area.lon)

    # ---- the questions CROVIA is allowed to ask -------------------------

    def verify_location(self, phone: str, area: Area,
                        district: str | None = None) -> dict:
        """
        Is this device inside this circle?

        The main paid sensor. Note what it does NOT return: coordinates. And
        note how often it returns nothing useful at all.
        """
        self.ledger.record(TIER_VERIFY, district)
        self._fail_sometimes()

        i = self.phone_to_index.get(phone)
        if i is None or not self.world.reachable[i]:
            return {"verification_result": "UNKNOWN"}
        if self.rng.random() < self.unknown_prob:
            return {"verification_result": "UNKNOWN"}

        ox, oy = self._observed_position(i)
        ax, ay = self._area_xy(area)
        d = math.hypot(ox - ax, oy - ay)
        # The uncertainty around the fix overlaps the circle by some amount;
        # a fix near the edge is honestly reported as PARTIAL rather than as a
        # confident yes or no.
        unc = RANDOM_ERROR_M
        if d + unc <= area.radius_m:
            return {"verification_result": "TRUE"}
        if d - unc >= area.radius_m:
            return {"verification_result": "FALSE"}
        overlap = (area.radius_m - (d - unc)) / max(2 * unc, 1.0)
        overlap = min(max(overlap, 0.0), 1.0)
        return {"verification_result": "PARTIAL", "match_rate": int(overlap * 100)}

    def get_reachability(self, phone: str, district: str | None = None) -> dict:
        self.ledger.record(TIER_REACHABILITY, district)
        self._fail_sometimes()
        i = self.phone_to_index.get(phone)
        if i is None:
            return {"reachable": False, "connectivity": []}
        ok = bool(self.world.reachable[i])
        return {"reachable": ok, "connectivity": ["DATA", "SMS"] if ok else []}

    def retrieve_location(self, phone: str, max_age_s: int = 90,
                          district: str | None = None) -> dict:
        """Coordinates, with an honest uncertainty radius. Three times the price."""
        self.ledger.record(TIER_RETRIEVE, district)
        self._fail_sometimes()
        i = self.phone_to_index.get(phone)
        if i is None or not self.world.reachable[i]:
            return {"status": "UNKNOWN"}
        if self.rng.random() < self.unknown_prob:
            return {"status": "UNKNOWN"}
        ox, oy = self._observed_position(i)
        lat = self.world.lat0 + oy / self.world.mlat
        lon = self.world.lon0 + ox / self.world.mlon
        return {"status": "OK", "latitude": lat, "longitude": lon,
                "radius": RANDOM_ERROR_M + CELL_BIAS_M}

    # ---- subscriptions --------------------------------------------------

    def create_congestion_subscription(self, phone: str, sink: str,
                                       expire_s: int) -> str:
        self.ledger.record(TIER_CONGESTION_SUB)
        self._seq += 1
        sid = f"sc-cong-{self._seq}"
        self.subs[sid] = {"kind": "congestion", "phone": phone, "sink": sink}
        return sid

    def create_geofence_subscription(self, phone: str, area_id: str, area: Area,
                                     sink: str, expire_s: int,
                                     initial_event: bool = True
                                     ) -> tuple[str, dict | None]:
        """
        Subscribe to area-entered for one circle.

        The return value is (id, None) exactly as the real client gives, because
        Nokia does not answer inline - it answers later, on the webhook. If the
        device is already inside and initial_event is set, an area-entered
        notification is POSTed straight away; if it is not inside, nothing is
        sent at all and CROVIA has to live with the silence.
        """
        self.ledger.record(TIER_GEOFENCE_SUB)
        self._seq += 1
        sid = f"sc-geo-{self._seq}"
        i = self.phone_to_index.get(phone)
        ax, ay = self._area_xy(area)
        inside = False
        if i is not None:
            ox, oy = self._observed_position(i)
            inside = math.hypot(ox - ax, oy - ay) <= area.radius_m
        self.subs[sid] = {"kind": "geofence", "phone": phone, "area": area_id,
                          "sink": sink, "inside": inside,
                          "center": (ax, ay), "radius": area.radius_m}
        if initial_event and inside:
            # Queued, not sent.
            #
            # Sending it here delivered the notification before the caller had
            # bound the subscription id to a device, so the handler could not
            # tell who it was about and dropped every one - every device ended
            # up in no district at all.
            #
            # Deferring is also closer to the truth: the real network answers a
            # moment later over HTTP, never inside the call that created the
            # subscription.
            self._pending_initial.append((sink, sid, phone, area_id))
        return sid, None

    def delete_subscription(self, sub_id: str) -> None:
        self.ledger.record(TIER_DELETE)
        self.subs.pop(sub_id, None)

    # ---- Quality on Demand ----------------------------------------------

    def create_qod_session(self, phone: str, server_ip: str, profile: str,
                           duration_s: int, sink: str | None = None) -> dict:
        self.ledger.record(TIER_QOD)
        self._seq += 1
        return {"session_id": f"sc-qod-{self._seq}", "status": "REQUESTED",
                "status_info": None, "expires_at": None}

    def delete_qod_session(self, session_id: str) -> None:
        self.ledger.record(TIER_DELETE)

    def extend_qod_session(self, session_id: str, extra_s: int) -> dict:
        return {"session_id": session_id, "status": "AVAILABLE"}

    # ---- what the network PUSHES, unasked -------------------------------

    def push_notifications(self, now: float) -> dict:
        """
        Send everything Nokia would have sent since the last call.

        Two kinds, both free to CROVIA and both arriving whenever the network
        feels like it rather than when the engine asks.
        """
        sent = {"geofence": 0, "congestion": 0}

        # Anything the subscriptions owed us from when they were created.
        for sink, sid, phone, area_id in self._pending_initial:
            self.webhook.geofence(sink, sid, phone, area_id, "area-entered")
            sent["geofence"] += 1
        self._pending_initial.clear()

        # Geofence: somebody has crossed into a circle they were outside of.
        for sid, s in self.subs.items():
            if s["kind"] != "geofence":
                continue
            i = self.phone_to_index.get(s["phone"])
            if i is None:
                continue
            ox, oy = self._observed_position(i)
            cx, cy = s["center"]
            now_inside = math.hypot(ox - cx, oy - cy) <= s["radius"]
            if now_inside and not s["inside"]:
                self.webhook.geofence(s["sink"], sid, s["phone"],
                                      s["area"], "area-entered")
                sent["geofence"] += 1
            # Leaving is tracked internally but never announced: CROVIA only
            # subscribes to area-entered, so the network has nothing to send.
            s["inside"] = now_inside

        # Congestion: a periodic report per device about its own cell.
        for sid, s in self.subs.items():
            if s["kind"] != "congestion":
                continue
            last = self._last_congestion.get(sid, -1e9)
            if now - last < CONGESTION_INTERVAL_S:
                continue
            self._last_congestion[sid] = now
            i = self.phone_to_index.get(s["phone"])
            if i is None or not self.world.reachable[i]:
                continue
            density = self.world.local_density(i)
            # Relative to an ordinary evening in that part of the city.
            ratio = density / self.baseline_density
            # Congestion that is nothing to do with crowds - somebody
            # streaming video on an otherwise empty street. Without it the
            # signal is cleaner than any real network would ever give, and the
            # comparison against the calmest district is never really tested.
            if self.congestion_noise:
                ratio += self.congestion_noise * 3.0 * float(
                    self.rng.uniform(0.7, 1.3))
            level = next(name for thr, name in CONGESTION_LEVELS if ratio >= thr)
            conf = int(self.rng.integers(*CONFIDENCE_RANGE))
            self.webhook.congestion(s["sink"], s["phone"], level, conf, now)
            sent["congestion"] += 1

        return sent
