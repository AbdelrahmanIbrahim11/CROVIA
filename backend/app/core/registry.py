"""
Who we are watching, and where they are.

Three separate ideas that are easy to confuse:

  VAULT      the real phone number, kept behind one guarded lookup. Everything
             else in the system uses a hash. A hash cannot be passed to the
             CAMARA APIs, so exactly one component is allowed to translate.

  SENTINELS  a small group per district. They carry congestion subscriptions
             and district geofences. Deliberately unbalanced, because we add
             more of them where an event is expected — which makes them good
             for locating a crowd and useless for counting one.

  PANEL      a uniform random sample of ALL app users, regardless of district.
             Too thin to locate anything, but its share of the population is
             known exactly, so the fraction of the panel standing inside a zone
             is an unbiased estimate of the fraction of the city standing there.

The split between the last two matters. Using the district fleet to count
people under-counts an event crowd by two to three times, because visitors
travel in and the district's assumed population no longer holds.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field


def hash_phone(phone: str) -> str:
    return hashlib.sha256(f"crovia:{phone}".encode()).hexdigest()[:16]


@dataclass
class Vault:
    _to_phone: dict[str, str] = field(default_factory=dict)

    def enroll(self, phone: str) -> str:
        h = hash_phone(phone)
        self._to_phone[h] = phone
        return h

    def phone_for(self, hashed: str) -> str | None:
        return self._to_phone.get(hashed)

    def __len__(self) -> int:
        return len(self._to_phone)


@dataclass
class DeviceRegistry:
    """
    The map that congestion is missing.

    A congestion notification carries no location and no device id — only the
    subscription id. Resolving that to a district is only possible because the
    district geofences tell us, for free and continuously, which device is
    where. Without this table congestion says "something is wrong somewhere".
    """

    vault: Vault = field(default_factory=Vault)
    sub_device: dict[str, str] = field(default_factory=dict)  # sub id -> hashed
    sub_kind: dict[str, str] = field(default_factory=dict)
    sub_area: dict[str, str] = field(default_factory=dict)
    device_district: dict[str, str] = field(default_factory=dict)  # hashed -> district
    seen_at: dict[str, float] = field(default_factory=dict)
    sentinels: set[str] = field(default_factory=set)
    panel: set[str] = field(default_factory=set)
    _by_district: dict[str, set] = field(default_factory=lambda: defaultdict(set))

    # ---- enrolment -------------------------------------------------------

    def add_sentinel(self, phone: str, declared_district: str | None = None) -> str:
        h = self.vault.enroll(phone)
        self.sentinels.add(h)
        if declared_district:
            # A signup hint, free but sometimes wrong. The geofence's initial
            # event corrects it at no extra cost.
            self.place(h, declared_district, 0.0)
        return h

    def add_panel(self, phone: str, declared_district: str | None = None) -> str:
        h = self.add_sentinel(phone, declared_district)
        self.panel.add(h)
        return h

    def bind_subscription(
        self, sub_id: str, hashed: str, kind: str, area_id: str
    ) -> None:
        self.sub_device[sub_id] = hashed
        self.sub_kind[sub_id] = kind
        self.sub_area[sub_id] = area_id

    # ---- location --------------------------------------------------------

    def place(self, hashed: str, district_id: str, t: float) -> None:
        old = self.device_district.get(hashed)
        if old and old != district_id:
            self._by_district[old].discard(hashed)
        self.device_district[hashed] = district_id
        self.seen_at[hashed] = t
        self._by_district[district_id].add(hashed)

    def remove_from(self, hashed: str, district_id: str) -> None:
        if self.device_district.get(hashed) == district_id:
            self.device_district.pop(hashed, None)
        self._by_district[district_id].discard(hashed)

    def district_of(self, hashed: str) -> str | None:
        return self.device_district.get(hashed)

    def fleet(self, district_id: str) -> list[str]:
        return list(self._by_district[district_id])

    def panel_members(self) -> list[str]:
        return list(self.panel)

    def panel_size(self) -> int:
        return len(self.panel)

    # ---- counting --------------------------------------------------------

    def people_from_panel(self, inside: int, checked: int, population: int) -> float:
        """
        Turn "15 of 45 panel members are inside" into a number of people.

        Unbiased, because the panel is a uniform sample of the whole city. This
        is the estimate the danger rules use; the district fleet is never used
        for counting.
        """
        if checked <= 0:
            return 0.0
        return (inside / checked) * population
