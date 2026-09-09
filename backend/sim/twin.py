"""
The digital twin: a synthetic Lusail with real pedestrian physics.

This is GROUND TRUTH, and the detection engine is never allowed to read it. The
engine sees only what the mocked CAMARA layer chooses to reveal. That
separation is what makes the measured precision mean anything.

Movement uses the Weidmann speed-density relation, the standard fundamental
diagram in pedestrian engineering:

    v(rho) = v0 * (1 - exp(-gamma * (1/rho - 1/rho_max)))

The consequence that matters: pedestrian throughput peaks near 2 people/m2 and
then COLLAPSES. Past that point adding people moves fewer of them. That is the
self-reinforcing trap behind real crowd disasters, and without it a simulated
crowd simply drains no matter how dense it gets, so no crush detector can be
tested at all.

Unlike the earlier version, this twin runs SEVERAL events at once, because two
crowds forming in different parts of the city at the same time is the case that
makes budget allocation matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.city import City

V_FREE = 1.34
GAMMA = 1.913
RHO_MAX = 5.4
RHO_CRITICAL = 4.0

AMBIENT, EGRESS, DONE = 0, 1, 2


def weidmann_speed(rho: np.ndarray) -> np.ndarray:
    rho = np.clip(rho, 1e-4, RHO_MAX - 1e-3)
    return np.clip(V_FREE * (1.0 - np.exp(-GAMMA * (1.0 / rho - 1.0 / RHO_MAX))), 0.02, V_FREE)


@dataclass
class Population:
    n_people: int = 30_000
    app_share: float = 1.0 / 3.0
    unreachable_share: float = 0.06
    seed: int = 7


@dataclass
class Event:
    """One crowd. Several of these can run at the same time."""

    zone_id: str
    n_attendees: int
    start_s: float = 0.0
    duration_s: float = 12 * 60.0
    label: str = ""
    # Multiplies the width of constrained links, to model opening extra gates.
    width_scale: float = 1.0


class Twin:
    def __init__(self, city: City, pop: Population | None = None,
                 events: list[Event] | None = None, dt: float = 5.0) -> None:
        self.city = city
        self.pop = pop or Population()
        self.events = events or []
        self.dt = dt
        self.t = 0.0
        self.rng = np.random.default_rng(self.pop.seed)

        self.seg_ids = list(city.segments.keys())
        self.seg_ix = {s: i for i, s in enumerate(self.seg_ids)}
        self._build_segments()
        self._build_people()
        self._build_events()
        self.history: list[dict] = []

    # ---- setup ----------------------------------------------------------

    def _build_segments(self) -> None:
        n = len(self.seg_ids)
        self.seg_len = np.zeros(n); self.seg_w = np.zeros(n)
        self.seg_area = np.zeros(n); self.seg_next = np.full(n, -1, int)
        self.seg_xy: list[np.ndarray] = []
        scale = {e.zone_id: e.width_scale for e in self.events if e.width_scale != 1.0}
        for i, sid in enumerate(self.seg_ids):
            s = self.city.segments[sid]
            w = s.width_m
            if s.zone_id in scale and s.risk >= 1.4:
                w *= scale[s.zone_id]
            self.seg_len[i] = s.length_m
            self.seg_w[i] = w
            self.seg_area[i] = s.length_m * w
            # Local metres, relative to the city centre.
            c = self.city.meta["center"]
            pts = np.array([[
                (p.lon - c["lon"]) * 111_320 * np.cos(np.radians(c["lat"])),
                (p.lat - c["lat"]) * 110_540,
            ] for p in s.points])
            self.seg_xy.append(pts)
            if s.drains_to and s.drains_to in self.seg_ix:
                self.seg_next[i] = self.seg_ix[s.drains_to]

    def _build_people(self) -> None:
        n = self.pop.n_people
        rng = self.rng
        c = self.city.meta["center"]
        ds = list(self.city.districts.values())
        w = np.array([d.radius_m ** 2 for d in ds], float); w /= w.sum()
        home = rng.choice(len(ds), size=n, p=w)
        self.home_district = np.array([ds[i].id for i in home], dtype=object)

        cx = np.array([(ds[i].center.lon - c["lon"]) * 111_320 * np.cos(np.radians(c["lat"])) for i in home])
        cy = np.array([(ds[i].center.lat - c["lat"]) * 110_540 for i in home])
        rad = np.array([ds[i].radius_m for i in home])
        th = rng.uniform(0, 2 * np.pi, n)
        r = rad * np.sqrt(rng.uniform(0, 1, n))
        self.x = cx + r * np.cos(th)
        self.y = cy + r * np.sin(th)
        self.home_xy = np.stack([cx, cy], 1)
        self.home_r = rad

        self.has_app = rng.random(n) < self.pop.app_share
        self.reachable = rng.random(n) > self.pop.unreachable_share
        self.mode = np.full(n, AMBIENT, np.int8)
        self.seg = np.full(n, -1, np.int32)
        self.s = np.zeros(n)
        self.n = n

    def _build_events(self) -> None:
        self.ev_ids: list[np.ndarray] = []
        self.ev_release: list[np.ndarray] = []
        self.ev_done: list[np.ndarray] = []
        self.ev_entry: list[int] = []
        taken = np.zeros(self.n, bool)
        for e in self.events:
            if e.n_attendees <= 0:
                self.ev_ids.append(np.array([], int)); self.ev_release.append(np.array([]))
                self.ev_done.append(np.array([], bool)); self.ev_entry.append(-1); continue
            free = np.where(~taken)[0]
            ids = self.rng.choice(free, size=min(e.n_attendees, free.size), replace=False)
            taken[ids] = True
            u = self.rng.beta(2.0, 2.2, ids.size)
            self.ev_ids.append(ids)
            self.ev_release.append(e.start_s + u * e.duration_s)
            self.ev_done.append(np.zeros(ids.size, bool))
            segs = self.city.segments_of(e.zone_id)
            self.ev_entry.append(self.seg_ix[segs[0].id] if segs else -1)

    # ---- stepping -------------------------------------------------------

    def step(self) -> dict:
        for k, e in enumerate(self.events):
            ids = self.ev_ids[k]
            if ids.size == 0 or self.ev_entry[k] < 0:
                continue
            due = (~self.ev_done[k]) & (self.ev_release[k] <= self.t)
            if due.any():
                pick = ids[due]
                self.ev_done[k][due] = True
                self.mode[pick] = EGRESS
                self.seg[pick] = self.ev_entry[k]
                self.s[pick] = self.rng.uniform(0, self.seg_len[self.ev_entry[k]] * 0.35, pick.size)

        self._move_ambient()
        seg_state = self._move_egress()
        self.t += self.dt
        snap = self._snapshot(seg_state)
        self.history.append(snap)
        return snap

    def _move_ambient(self) -> None:
        amb = self.mode == AMBIENT
        k = int(amb.sum())
        if k == 0:
            return
        step = self.rng.normal(0, 0.6 * self.dt, (k, 2))
        dx = self.home_xy[amb, 0] - self.x[amb]
        dy = self.home_xy[amb, 1] - self.y[amb]
        d = np.hypot(dx, dy) + 1e-6
        pull = np.clip((d - self.home_r[amb] * 0.75) / 200.0, 0, 1)[:, None]
        drift = np.stack([dx / d, dy / d], 1) * pull * 0.8 * self.dt
        self.x[amb] += step[:, 0] + drift[:, 0]
        self.y[amb] += step[:, 1] + drift[:, 1]

    def _move_egress(self) -> dict:
        n = len(self.seg_ids)
        eg_mask = self.mode == EGRESS
        occ = (np.bincount(self.seg[eg_mask], minlength=n)
               if eg_mask.any() else np.zeros(n, int))
        density = np.divide(occ, self.seg_area, out=np.zeros(n), where=self.seg_area > 0)
        speed = weidmann_speed(density)
        state = {self.seg_ids[i]: {"occupancy": int(occ[i]), "density": float(density[i])}
                 for i in range(n)}

        eg = np.where(eg_mask)[0]
        if eg.size == 0:
            return state
        idx = self.seg[eg]
        self.s[eg] += speed[idx] * self.dt

        at_end = self.s[eg] >= self.seg_len[idx]
        movers = eg[at_end]
        if movers.size:
            cur = self.seg[movers]
            nxt = self.seg_next[cur]
            leaving = movers[nxt < 0]
            self.mode[leaving] = DONE
            self.seg[leaving] = -1
            cont = movers[nxt >= 0]
            if cont.size:
                tgt = self.seg_next[self.seg[cont]]
                # A link has a hard capacity. When it is full the queue must
                # back up into the link behind it — that is how a crush spreads.
                room = np.maximum(RHO_MAX * 0.97 * self.seg_area - occ, 0).astype(int)
                ok = np.zeros(cont.size, bool)
                for t in np.unique(tgt):
                    here = np.where(tgt == t)[0]
                    free = int(room[t])
                    if free <= 0:
                        continue
                    take = here if here.size <= free else self.rng.choice(here, free, replace=False)
                    ok[take] = True
                    room[t] -= int(np.size(take))
                acc, blocked = cont[ok], cont[~ok]
                if acc.size:
                    self.seg[acc] = tgt[ok]; self.s[acc] = 0.0
                if blocked.size:
                    self.s[blocked] = self.seg_len[self.seg[blocked]] - 0.01
        self._update_xy()
        return state

    def _update_xy(self) -> None:
        eg = np.where(self.mode == EGRESS)[0]
        if eg.size == 0:
            return
        for i in np.unique(self.seg[eg]):
            if i < 0:
                continue
            mem = eg[self.seg[eg] == i]
            pts = self.seg_xy[int(i)]
            frac = np.clip(self.s[mem] / max(self.seg_len[int(i)], 1e-6), 0, 1)
            segl = np.hypot(*(pts[1:] - pts[:-1]).T)
            cum = np.concatenate([[0], np.cumsum(segl)])
            target = frac * cum[-1]
            j = np.clip(np.searchsorted(cum, target, "right") - 1, 0, len(segl) - 1)
            loc = (target - cum[j]) / np.maximum(segl[j], 1e-6)
            a, b = pts[j], pts[j + 1]
            px = a[:, 0] + (b[:, 0] - a[:, 0]) * loc
            py = a[:, 1] + (b[:, 1] - a[:, 1]) * loc
            half = self.seg_w[int(i)] / 2
            off = self.rng.uniform(-half, half, mem.size)
            d = pts[-1] - pts[0]
            nx, ny = -d[1], d[0]
            nn = np.hypot(nx, ny) + 1e-6
            self.x[mem] = px + off * nx / nn
            self.y[mem] = py + off * ny / nn

    def _snapshot(self, seg_state: dict) -> dict:
        per_zone = {}
        for zid in self.city.zones:
            segs = self.city.segments_of(zid)
            worst, wd = None, 0.0
            people = 0
            for s in segs:
                st = seg_state.get(s.id, {})
                people += st.get("occupancy", 0)
                if st.get("density", 0.0) > wd:
                    worst, wd = s.id, st["density"]
            per_zone[zid] = {"worst_segment": worst, "worst_density": wd, "people": people}
        return {"t": self.t, "segments": seg_state, "zones": per_zone,
                "n_egress": int((self.mode == EGRESS).sum()),
                "n_done": int((self.mode == DONE).sum())}

    def people_in_zone(self, zone_id: str) -> int:
        """Ground truth headcount inside the zone circle. Scoring only."""
        z = self.city.zones[zone_id]
        c = self.city.meta["center"]
        zx = (z.center.lon - c["lon"]) * 111_320 * np.cos(np.radians(c["lat"]))
        zy = (z.center.lat - c["lat"]) * 110_540
        return int((np.hypot(self.x - zx, self.y - zy) <= z.radius_m).sum())
