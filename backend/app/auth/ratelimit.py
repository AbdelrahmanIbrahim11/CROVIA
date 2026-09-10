"""
Slowing down password guessing.

Without this, an open login endpoint can be tried as fast as the network
allows. bcrypt at 12 rounds is deliberately slow, which helps, but it is a
speed bump rather than a stop: a few hundred attempts a minute against a
short password still gets there.

Two counters, and the reason there are two:

  BY EMAIL    stops one account being ground down, even when the attempts come
              from many machines.
  BY ADDRESS  stops one machine working through a list of emails, which the
              per-email counter would never notice.

Held in memory. That is honest about what it is: it resets when the service
restarts, and two copies of the service each keep their own count. It raises
the cost of guessing without pretending to be the finished article. When there
is a Redis instance, move the two dictionaries into it and nothing else here
changes.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

# Attempts allowed inside the window, per email and per address.
MAX_PER_EMAIL = 8
MAX_PER_ADDRESS = 30
WINDOW_S = 300.0  # five minutes

_by_email: dict[str, deque[float]] = defaultdict(deque)
_by_address: dict[str, deque[float]] = defaultdict(deque)


def _trim(hits: deque[float], now: float) -> None:
    while hits and now - hits[0] > WINDOW_S:
        hits.popleft()


def check(email: str, address: str) -> float | None:
    """
    How many seconds to wait, or None when the attempt may proceed.

    Called before the password is checked, so a blocked attempt costs neither a
    bcrypt comparison nor a database read.
    """
    now = time.monotonic()
    key = email.strip().lower()

    for hits, limit in ((_by_email[key], MAX_PER_EMAIL),
                        (_by_address[address], MAX_PER_ADDRESS)):
        _trim(hits, now)
        if len(hits) >= limit:
            return max(1.0, WINDOW_S - (now - hits[0]))
    return None


def record_failure(email: str, address: str) -> None:
    """
    Count a failed attempt.

    Only failures count. A person signing in correctly ten times in a morning
    is not attacking anything, and locking them out would be the rate limiter
    causing the outage it exists to prevent.
    """
    now = time.monotonic()
    _by_email[email.strip().lower()].append(now)
    _by_address[address].append(now)


def clear(email: str, address: str) -> None:
    """Forget the failures after a successful sign-in."""
    _by_email.pop(email.strip().lower(), None)
    _by_address.pop(address, None)
