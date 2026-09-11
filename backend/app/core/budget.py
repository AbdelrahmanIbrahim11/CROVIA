"""
Spend control, and how it is shared when more than one crowd needs attention.

Two jobs:

  1. Count what every API call costs, by kind, so the cost story is measured
     rather than estimated.

  2. Decide who gets the money when two places are dangerous at the same time.

The second job is the one that only appears once the city has more than one
crowd. A single incident can simply spend what it needs. Two incidents compete,
and with a fixed hourly budget the wrong split means one of them is watched
properly while the other is watched too late to matter.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

# What each kind of call costs us, in "call" units. Congestion and geofence
# notifications are pushed by the network, so listening is free; only creating
# and deleting subscriptions is billed here.
TIER_CONGESTION_SUB = "congestion_subscription"
TIER_GEOFENCE_SUB = "geofence_subscription"
TIER_DELETE = "subscription_delete"
TIER_VERIFY = "location_verification"
TIER_REACHABILITY = "reachability"
TIER_RETRIEVE = "location_retrieval"
# A priority session is billed for as long as it lives, not per call, so it is
# counted once when opened. The weight is high because a session held for an
# hour is not comparable to a single question about one device.
TIER_QOD = "priority_session"

# Relative expense. Verification is cheap because it needs no subscription and
# returns no coordinates; retrieval is the expensive one.
TIER_WEIGHT = {
    TIER_CONGESTION_SUB: 1.0,
    TIER_GEOFENCE_SUB: 1.0,
    TIER_DELETE: 0.5,
    TIER_VERIFY: 1.0,
    TIER_REACHABILITY: 0.5,
    TIER_RETRIEVE: 3.0,
    TIER_QOD: 5.0,
}


@dataclass
class Ledger:
    calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    by_district: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, tier: str, district_id: str | None = None) -> None:
        self.calls[tier] += 1
        if district_id:
            self.by_district[district_id] += 1

    def record_error(self, status: int) -> None:
        self.errors[status] += 1

    @property
    def total(self) -> int:
        return sum(self.calls.values())

    @property
    def weighted(self) -> float:
        return sum(TIER_WEIGHT.get(k, 1.0) * v for k, v in self.calls.items())

    def summary(self) -> dict:
        return {
            "total": self.total,
            "weighted": round(self.weighted, 1),
            "by_tier": dict(self.calls),
            "by_district": dict(self.by_district),
            "errors": {str(k): v for k, v in self.errors.items()},
        }


@dataclass
class Request:
    """One district asking to spend."""

    district_id: str
    zone_id: str
    calls_wanted: int
    # 0..1, how strongly the evidence says this place is becoming dangerous.
    severity: float
    # People already estimated inside. A bigger crowd is worth more attention.
    people: float
    # Seconds until this is expected to become critical, if known.
    seconds_to_critical: float | None = None

    def priority(self) -> float:
        """
        Higher wins when budget is short.

        Urgency dominates. A place that becomes dangerous in three minutes has
        to be resolved before one that becomes dangerous in twenty, even if the
        second is larger — because for the second there is still time to come
        back to it, and for the first there is not.
        """
        urgency = 1.0
        if self.seconds_to_critical is not None:
            urgency = max(1.0, 900.0 / max(self.seconds_to_critical, 60.0))
        size = min(self.people / 5000.0, 2.0)
        return self.severity * urgency * (1.0 + size)


class Budget:
    """A rolling hourly cap, with a reserve held back for scheduled events."""

    def __init__(self, per_hour: int = 6000, reserve_fraction: float = 0.35) -> None:
        self.per_hour = per_hour
        self.reserve_fraction = reserve_fraction
        self._spent: deque[float] = deque()
        self._reserved_until: float | None = None

    def _prune(self, now: float) -> None:
        while self._spent and now - self._spent[0] > 3600:
            self._spent.popleft()

    def spend(self, n: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._prune(now)
        for _ in range(n):
            self._spent.append(now)

    def remaining(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        self._prune(now)
        return max(0, self.per_hour - len(self._spent))

    def available(self, now: float | None = None) -> int:
        """
        What may be spent right now.

        While a scheduled event is approaching, part of the budget is held back
        so an ordinary busy evening cannot use up the money that the stadium
        will need when it empties.
        """
        now = time.time() if now is None else now
        free = self.remaining(now)
        if self._reserved_until and now < self._reserved_until:
            free -= int(self.per_hour * self.reserve_fraction)
        return max(0, free)

    def hold_reserve_until(self, ts: float) -> None:
        self._reserved_until = ts

    def release_reserve(self) -> None:
        self._reserved_until = None

    # ------------------------------------------------------------------

    def allocate(self, requests: list[Request], now: float | None = None) -> dict[str, int]:
        """
        Split what is available between competing districts.

        Ordered by priority, and each request is either funded properly or not
        at all. Spreading a thin budget evenly across three incidents produces
        three answers too weak to act on, which is worse than one answer that is
        solid and two that are honestly marked as unresolved.
        """
        pot = self.available(now)
        out: dict[str, int] = {}
        for r in sorted(requests, key=lambda r: r.priority(), reverse=True):
            if pot <= 0:
                out[r.zone_id] = 0
                continue
            # Never fund less than a third of what was asked for; below that the
            # sample is too small to conclude anything.
            floor = max(1, r.calls_wanted // 3)
            grant = min(r.calls_wanted, pot)
            out[r.zone_id] = grant if grant >= floor else 0
            pot -= out[r.zone_id]
        return out
