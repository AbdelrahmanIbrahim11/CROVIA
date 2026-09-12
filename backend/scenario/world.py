"""
A city of real people, with no detector anywhere near it.

This is the ground truth for the honest test, and it is deliberately NOT the
twin. It exists because the twin, while a fair test in some ways, carries three
assumptions that flatter the system, and this file removes all three.

WHAT WAS WRONG WITH THE TWIN, AND WHAT IS DIFFERENT HERE
--------------------------------------------------------

1. THE TWIN GAVE EVERY PERSON THE SAME CHANCE OF HAVING THE APP.

   `has_app = rng.random(n) < 1/3` spreads app users perfectly evenly across the
   population, which makes the panel a flawless random sample and the headcount
   unbiased BY CONSTRUCTION. That is the single most flattering assumption in
   the whole project, because the entire counting method rests on the panel
   being representative.

   Real app users cluster. They are younger, wealthier, more urban, and they are
   not spread evenly across four districts. Here, app ownership is deliberately
   UNEVEN per district (see APP_SHARE_BY_DISTRICT), so the panel
   over-represents some parts of the city and under-represents others. The
   headcount is therefore wrong in a way the twin could never reveal.

2. THE TWIN AND THE DETECTOR AGREED ON HOW MANY PEOPLE EXIST.

   Both used exactly 30,000, so the estimate
   `(inside / checked) * population` multiplied by a number that was perfectly
   correct. In a real city nobody knows the live population; it changes hour by
   hour with commuters and visitors.

   Here the number of people actually present is PRESENT_SHARE of the planned
   figure, so the detector multiplies by a denominator that is genuinely a
   little wrong, exactly as it would be in Lusail.

3. THE TWIN'S MAP WAS PERFECT.

   The detector read the same widths the physics used, so it always knew the
   true width of every link. Reality puts a parked van in the ramp, or closes a
   gate. WIDTH_ERROR lets a link be narrower in truth than the plan believes,
   which is the failure mode that makes a confident capacity figure dangerous.

WHAT IS DELIBERATELY NOT CIRCULAR
---------------------------------
The detector's whole rule rests on `people per minute = width * 72`. Nothing in
this file uses that formula. Movement here is limited by space and speed: a link
holds only so many bodies at jam density, and people walk slower as it fills.
The throughput of a narrow link EMERGES from that, and is never imposed.

So when the detector's arithmetic predicts what this world does, that is a
result rather than a restatement.

NOTHING IN THIS FILE IS EVER VISIBLE TO THE ENGINE. The only way anything here
reaches CROVIA is through scenario/network.py, which answers the same CAMARA
questions Nokia answers, with the same errors and the same silences.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np

from app.core.city import city
from scenario.catalogue import CATALOGUE, Spec

# ===========================================================================
# TUNABLES - this is the part to edit
# ===========================================================================

# How many people the city PLAN says live here. CROVIA reads this from the map
# file and multiplies by it. It is a planning figure, not a live count.
PLANNED_POPULATION = 30_000

# How many of them are actually in the city during the test. Anything other
# than 1.0 means CROVIA's headcount is scaled by a denominator that is wrong,
# which is the normal condition in a real city.
PRESENT_SHARE = 0.92

# How many people have the app, as a share of those present.
APP_SHARE = 1.0 / 3.0

# THE IMPORTANT ONE. How app ownership is distributed between districts.
#
# Equal values here reproduce the twin's flattering assumption. Unequal values
# are realistic: a young, dense, central district has far higher app ownership
# than an outlying one. These are multipliers on the city-wide APP_SHARE and
# are normalised, so their absolute size does not matter - only their ratios.
APP_SHARE_BY_DISTRICT = {
    "district_central": 1.8,     # young, dense, high smartphone use
    "district_stadium": 1.1,
    "district_marina": 0.9,
    "district_foxhills": 0.4,    # older, residential, low app uptake
}

# Truth vs the plan, per segment. A value below 1.0 means the link is NARROWER
# in reality than the map believes - a barrier, a parked vehicle, a closed gate.
# CROVIA will compute capacity from the plan and be confidently wrong.
# Leave empty for a perfect map.
WIDTH_ERROR: dict[str, float] = {
    # "seg_concourse_ramp": 0.78,
}

# Walking. v0 is free speed; people slow as the ground fills.
FREE_WALK_SPEED = 1.34        # m/s
JAM_DENSITY = 5.4             # people/m2 - nobody moves at all
CRITICAL_DENSITY = 4.0        # people/m2 - control of movement is lost

SEED = 11


# ===========================================================================
# The event schedule
# ===========================================================================



# ===========================================================================
# The world
# ===========================================================================

AT_HOME, TRAVELLING, IN_BOWL, LEAVING, GONE = 0, 1, 2, 3, 4


class World:
    """
    Every person in Lusail, where they are, and what they are doing.

    Positions are metres on a flat plane centred on the city, which is accurate
    enough over a few kilometres and keeps the movement code readable.
    """

    def __init__(self, spec: Spec | None = None, seed: int | None = None) -> None:
        """
        Build a city for one scenario.

        Everything that differs between scenarios arrives in the spec, so the
        physics here is identical in every run - which is what makes comparing
        two scenarios meaningful.
        """
        self.spec = spec or CATALOGUE[0]
        # Seed comes from the environment when not given, so a run can be
        # repeated exactly or varied deliberately.
        #
        # This was lost once to a later rewrite of this file and the loss was
        # silent: every "different seed" produced the identical evening, so
        # three runs agreeing meant nothing at all. Checked explicitly now
        # rather than assumed.
        if seed is None:
            seed = int(os.getenv("CROVIA_SCENARIO_SEED", SEED))
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.n = int(PLANNED_POPULATION * self.spec.present_share)

        self._build_geometry()
        self._build_people()
        self._assign_app()
        self._choose_attendees()

    # ---- geometry ------------------------------------------------------

    def _build_geometry(self) -> None:
        """Metres-from-centre for every district and zone, plus the egress route."""
        c = city.meta["center"]
        self.lat0, self.lon0 = c["lat"], c["lon"]
        self.mlat = 111_320.0
        self.mlon = 111_320.0 * math.cos(math.radians(self.lat0))

        self.districts = {}
        for did, d in city.districts.items():
            self.districts[did] = (self._to_xy(d.center.lat, d.center.lon), d.radius_m)

        self.zones = {}
        for zid, z in city.zones.items():
            self.zones[zid] = (self._to_xy(z.center.lat, z.center.lon), z.radius_m)

        # The egress route: the chain of segments people walk through on the way
        # out, with the TRUE width of each (which may differ from the plan).
        self.route = []
        for seg in city.segments_of(self.spec.egress_zone):
            true_width = seg.width_m * self.spec.width_error.get(seg.id, 1.0)
            self.route.append({
                "id": seg.id,
                "label": seg.label,
                "plan_width": seg.width_m,
                "true_width": true_width,
                "length": seg.length_m,
                "area": true_width * seg.length_m,
                "mid": self._to_xy(*self._segment_midpoint(seg)),
                "occupants": 0,
            })

    def _segment_midpoint(self, seg) -> tuple[float, float]:
        pts = seg.points
        mid = pts[len(pts) // 2]
        return (mid.lat, mid.lon)

    def _to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lon - self.lon0) * self.mlon, (lat - self.lat0) * self.mlat)

    # ---- people --------------------------------------------------------

    def _build_people(self) -> None:
        """Scatter people across the districts they live in."""
        dids = list(self.districts)
        # Districts hold different numbers of people; this is their share.
        weights = np.array([1.3, 1.0, 1.5, 0.8])
        weights = weights / weights.sum()
        self.home_district = self.rng.choice(dids, size=self.n, p=weights)

        self.x = np.zeros(self.n)
        self.y = np.zeros(self.n)
        for did in dids:
            idx = np.where(self.home_district == did)[0]
            (cx, cy), r = self.districts[did]
            ang = self.rng.uniform(0, 2 * np.pi, idx.size)
            rad = r * np.sqrt(self.rng.uniform(0, 1, idx.size))
            self.x[idx] = cx + rad * np.cos(ang)
            self.y[idx] = cy + rad * np.sin(ang)

        self.mode = np.full(self.n, AT_HOME, dtype=int)
        self.route_pos = np.full(self.n, -1, dtype=int)   # index into self.route
        # When each person finishes crossing their current segment. Latency,
        # kept separate from how many the segment can discharge per second.
        self.ready_at = np.zeros(self.n)
        self.reachable = self.rng.random(self.n) > 0.06

    def _assign_app(self) -> None:
        """
        Decide who has the app - UNEVENLY, by district.

        This is the correction that matters most. The twin gave everybody the
        same chance, which quietly guaranteed the panel was a perfect sample.
        """
        target = int(self.n * APP_SHARE)
        raw = np.array([self.spec.app_share_by_district.get(d, 1.0)
                        for d in self.home_district])
        p = raw / raw.sum() * target
        p = np.clip(p, 0.0, 1.0)
        self.has_app = self.rng.random(self.n) < p

    def _choose_attendees(self) -> None:
        """
        Who goes to the match.

        Drawn from the whole city, not just the stadium district, because
        visitors travel in - which is exactly what breaks any estimate based on
        a district's usual population.
        """
        pool = np.arange(self.n)
        take = max(0, min(self.spec.attendees, self.n))
        self.attendee = np.zeros(self.n, dtype=bool)
        if take:
            self.attendee[self.rng.choice(pool, size=take, replace=False)] = True

        # Where the bowl is: just inside the stadium district, offset from the
        # ramp so that sitting in the stadium does NOT put you in the zone.
        (zx, zy), _ = self.zones[self.spec.egress_zone]
        (dx, dy), _ = self.districts["district_stadium"]
        vx, vy = dx - zx, dy - zy
        norm = math.hypot(vx, vy) or 1.0
        self.bowl = (zx + vx / norm * 700.0, zy + vy / norm * 700.0)

    # ---- movement ------------------------------------------------------

    def step(self, dt: float, phase: str) -> None:
        """Advance the world. The detector never sees any of this."""
        self.t += dt
        if phase == "calm":
            self._wander(dt)
        elif phase == "arrival":
            self._wander(dt)
            self._travel_to_bowl(dt)
        elif phase == "match":
            self._wander(dt, only_non_attendees=True)
        elif phase == "egress":
            self._wander(dt, only_non_attendees=True)
            self._egress(dt)
        elif phase == "dispersal":
            self._wander(dt, only_non_attendees=True)
            self._egress(dt)
            self._walk_away(dt)

    def _wander(self, dt: float, only_non_attendees: bool = False) -> None:
        """Ordinary background movement - people going about their evening."""
        who = self.mode == AT_HOME
        if only_non_attendees:
            who &= ~self.attendee
        idx = np.where(who)[0]
        if idx.size == 0:
            return
        step = self.rng.normal(0, 0.5 * dt, (idx.size, 2))
        self.x[idx] += step[:, 0]
        self.y[idx] += step[:, 1]
        # Keep them roughly inside their own district.
        for did in self.districts:
            sel = idx[self.home_district[idx] == did]
            if sel.size == 0:
                continue
            (cx, cy), r = self.districts[did]
            dx, dy = self.x[sel] - cx, self.y[sel] - cy
            d = np.hypot(dx, dy)
            out = d > r
            if out.any():
                s = sel[out]
                self.x[s] = cx + dx[out] / d[out] * r * 0.98
                self.y[s] = cy + dy[out] / d[out] * r * 0.98

    def _travel_to_bowl(self, dt: float) -> None:
        """Attendees make their way to the stadium and go inside."""
        moving = np.where(self.attendee & (self.mode == AT_HOME))[0]
        if moving.size:
            # A steady trickle starts travelling, not everyone at once.
            start = self.rng.random(moving.size) < (dt / 600.0)
            self.mode[moving[start]] = TRAVELLING

        trav = np.where(self.mode == TRAVELLING)[0]
        if trav.size == 0:
            return
        bx, by = self.bowl
        dx, dy = bx - self.x[trav], by - self.y[trav]
        d = np.hypot(dx, dy)
        speed = FREE_WALK_SPEED * 4.0        # they are driving or on the tram
        move = np.minimum(speed * dt, d)
        self.x[trav] += np.where(d > 0, dx / d, 0) * move
        self.y[trav] += np.where(d > 0, dy / d, 0) * move
        arrived = trav[d <= speed * dt]
        self.mode[arrived] = IN_BOWL
        # Seated, packed tightly, and completely safe.
        self.x[arrived] = bx + self.rng.normal(0, 90, arrived.size)
        self.y[arrived] = by + self.rng.normal(0, 90, arrived.size)

    def _egress(self, dt: float) -> None:
        """
        The crowd leaves. Two separate things decide how fast.

        HOW LONG IT TAKES TO CROSS a link - its latency. A 631 m approach walk
        takes eight minutes at free speed and longer when it is full, because
        walking speed falls as the ground fills.

        HOW MANY CAN LEAVE IT PER SECOND - its discharge. Flow is density x
        speed x width, which peaks at half the jam density, so a 9 m link tops
        out near 977 people a minute however many are queued behind.

        Two earlier versions each collapsed these into one number and both were
        wrong. Letting a fraction of a segment's occupants exit each tick made a
        long walkway behave as if it had low capacity, when it merely takes a
        while to cross. Moving everyone at the speed implied by the segment's
        average density then froze the ramp solid once it jammed - but a jammed
        link keeps discharging at its front while the congestion sits upstream,
        which is why real crowds eventually clear.

        Nothing here uses `width * 72`. The discharge figure falls out of the
        walking model, and it disagrees with the detector's rule of thumb - 977
        against 648 for the ramp - which is precisely what makes this a test.
        """
        # Leave the seats. At full time a bowl empties in minutes; what holds
        # people up is the exits, not their willingness to go.
        inside = np.where(self.mode == IN_BOWL)[0]
        if inside.size:
            rate = dt / 300.0 * self.spec.release_rate
            leaving = inside[self.rng.random(inside.size) < rate]
            first = self.route[0]
            room = max(0, int(JAM_DENSITY * first["area"]) - first["occupants"])
            take = leaving[:room]
            if take.size:
                self.mode[take] = LEAVING
                self.route_pos[take] = 0
                self._enter(take, 0)

        for i, seg in enumerate(self.route):
            seg["occupants"] = int(np.count_nonzero(
                (self.mode == LEAVING) & (self.route_pos == i)))

        # Front of the route first, so room freed ahead is usable behind within
        # the same tick - which is how a queue actually drains.
        for i in range(len(self.route) - 1, -1, -1):
            seg = self.route[i]
            here = np.where((self.mode == LEAVING) & (self.route_pos == i))[0]
            if here.size == 0:
                continue

            # Who has finished crossing and is now waiting at the far end.
            ready = here[self.ready_at[here] <= self.t]
            if ready.size == 0:
                self._place_on_segment(here, seg)
                continue

            # The link can only pass so many per second, however many are queued.
            max_out = max(1, int(self._discharge_per_s(seg["true_width"]) * dt))
            movers = ready[:max_out]

            if i == len(self.route) - 1:
                self.mode[movers] = GONE
                self.route_pos[movers] = -1
                seg["occupants"] -= int(movers.size)
            else:
                nxt = self.route[i + 1]
                room = max(0, int(JAM_DENSITY * nxt["area"]) - nxt["occupants"])
                accepted = movers[:room]
                if accepted.size:
                    self.route_pos[accepted] = i + 1
                    self._enter(accepted, i + 1)
                    nxt["occupants"] += int(accepted.size)
                    seg["occupants"] -= int(accepted.size)

            self._place_on_segment(
                np.where((self.mode == LEAVING) & (self.route_pos == i))[0], seg)

    def _enter(self, idx: np.ndarray, seg_index: int) -> None:
        """
        Start somebody crossing a segment, and work out when they reach the end.

        Crossing time comes from the density already on it, so a link that is
        filling up slows the people entering it. That is the congestion effect;
        the discharge cap above is the capacity effect, and they are different.
        """
        if idx.size == 0:
            return
        seg = self.route[seg_index]
        density = seg["occupants"] / max(seg["area"], 1.0)
        speed = self._speed_at(density)
        self.ready_at[idx] = self.t + seg["length"] / max(speed, 0.05)

    def _discharge_per_s(self, width: float) -> float:
        """
        The most a link of this width can pass, per second.

        Flow is density x speed x width. With speed falling linearly to zero at
        jam density, that product peaks at half the jam density, giving
        v0 * rho_max / 4 per metre of width. Derived here from the walking
        model, never taken from the detector's own rule.
        """
        return FREE_WALK_SPEED * JAM_DENSITY / 4.0 * width

    def _speed_at(self, density: float) -> float:
        """
        Walking speed falls as the ground fills, and reaches zero at jam.

        A straight fundamental-diagram relation. The point that matters is that
        throughput PEAKS and then collapses, which is the mechanism behind real
        crush events - without it a crowd simply drains however dense it gets
        and no detector could ever be tested.
        """
        if density <= 0:
            return FREE_WALK_SPEED
        return max(0.05, FREE_WALK_SPEED * (1.0 - density / JAM_DENSITY))

    def _place_on_segment(self, idx: np.ndarray, seg: dict) -> None:
        if idx.size == 0:
            return
        mx, my = seg["mid"]
        spread = max(seg["length"] / 2.0, 20.0)
        self.x[idx] = mx + self.rng.normal(0, spread * 0.4, idx.size)
        self.y[idx] = my + self.rng.normal(0, spread * 0.4, idx.size)

    def _walk_away(self, dt: float) -> None:
        gone = np.where(self.mode == GONE)[0]
        if gone.size == 0:
            return
        ang = self.rng.uniform(0, 2 * np.pi, gone.size)
        self.x[gone] += np.cos(ang) * FREE_WALK_SPEED * dt * 2
        self.y[gone] += np.sin(ang) * FREE_WALK_SPEED * dt * 2

    # ---- questions the network is allowed to answer ---------------------

    def inside_circle(self, i: int, cx: float, cy: float, r: float) -> bool:
        return math.hypot(self.x[i] - cx, self.y[i] - cy) <= r

    def district_of(self, i: int) -> str | None:
        for did, ((cx, cy), r) in self.districts.items():
            if self.inside_circle(i, cx, cy, r):
                return did
        return None

    def local_density(self, i: int, radius: float = 250.0) -> float:
        """People per square metre around one person - drives cell congestion."""
        dx, dy = self.x - self.x[i], self.y - self.y[i]
        n = int(np.count_nonzero(dx * dx + dy * dy <= radius * radius))
        return n / (math.pi * radius * radius)

    # ---- truth, for the report only -------------------------------------

    def truth(self) -> dict:
        """What really happened. Printed at the end; never given to CROVIA."""
        (zx, zy), zr = self.zones[self.spec.egress_zone]
        d = np.hypot(self.x - zx, self.y - zy)
        in_zone = int(np.count_nonzero(d <= zr))
        worst = max(
            (s["occupants"] / max(s["area"], 1.0), s["label"], s["true_width"])
            for s in self.route)
        return {
            "people_present": self.n,
            "app_users": int(self.has_app.sum()),
            "in_egress_zone": in_zone,
            "still_in_bowl": int(np.count_nonzero(self.mode == IN_BOWL)),
            "on_the_route": int(np.count_nonzero(self.mode == LEAVING)),
            "worst_density": round(worst[0], 2),
            "worst_link": worst[1],
            "worst_link_true_width": worst[2],
            "dangerous_now": worst[0] >= CRITICAL_DENSITY,
        }
