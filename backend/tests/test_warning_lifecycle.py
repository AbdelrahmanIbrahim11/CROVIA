"""
A warning has to end.

These exist because of a gap that was invisible from the code and obvious to a
person using the app: a warning said "avoid this place" and then sat there
unchanged for ever. Nothing expired it, nothing withdrew it, and nothing ever
said the crowd had gone. Somebody opening the app an hour later read a
live-looking warning about a ramp that had been empty for fifty minutes.

The database already knew - an incident records ended_at the moment the alert
clears. It was simply never read back to the person who had been warned.

    PYTHONPATH=. ./venv/bin/python tests/test_warning_lifecycle.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

os.environ["JWT_SECRET"] = "a-test-secret-long-enough-for-sha256"
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mkdtemp() + "/wl.db"
os.environ["NOKIA_NAC_API_KEY"] = ""
os.environ["CROVIA_TWIN"] = "0"

from app.core.registry import DeviceRegistry, hash_phone  # noqa: E402
from app.services import enrollment, incidents, warnings  # noqa: E402
from app.usersDB.db import (add_alert_delivery_kind, create_table,  # noqa: E402
                            getdb)
from app.usersDB.models import alert_delivery  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"  {'pass' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


ZONE = "zone_stadium_north_concourse"
RECORD = {
    "zone_id": ZONE, "segment": "seg_concourse_ramp",
    "segment_label": "North ramp narrows", "width_m": 9.0,
    "capacity_per_min": 648, "people_low": 5000, "people_high": 10000,
    "pinch_density": 2.4, "reason": "filling", "fired_by": "filling",
}


def run() -> int:
    create_table()
    add_alert_delivery_kind()
    db = next(getdb())
    registry = DeviceRegistry()

    # Two people who agreed to be watched, both in the affected district.
    phones = [f"+9743{uuid.uuid4().int % 10**7:07d}" for _ in range(2)]
    for p in phones:
        enrollment.grant_consent(db, p)
        enrollment.enrol(db, p, enrollment.PANEL)
        h = registry.add_sentinel(p)
        registry.place(h, "district_stadium", 0.0)
    me = hash_phone(phones[0])

    print("\n-- while the crowd is building ------------------------------------")
    row = incidents.open_incident(db, RECORD)
    sent = warnings.warn_people_near(db, registry, RECORD, incident_id=row.id)
    check("both people are warned", sent["sent"] == 2, f"{sent['sent']} sent")

    box = warnings.inbox(db, me)
    check("the warning is marked active", box and box[0]["active"] is True)
    check("it is a warning, not an all-clear", box[0]["kind"] == "warning")
    check("it carries its age", box[0]["age_seconds"] is not None,
          "so a stale one can be shown as stale")
    check("no end time yet", box[0]["ended_at"] is None)

    print("\n-- the crowd disperses -------------------------------------------")
    incidents.close_incident(db, ZONE)
    cleared = warnings.all_clear(db, row.id, ZONE)
    check("everyone warned is told it is over", cleared["sent"] == 2,
          f"{cleared['sent']} told")

    box = warnings.inbox(db, me)
    kinds = [w["kind"] for w in box]
    check("the person now has two messages", len(box) == 2, f"{kinds}")

    warning_row = next(w for w in box if w["kind"] == "warning")
    clear_row = next(w for w in box if w["kind"] == "all_clear")

    # The regression this file exists for.
    check("the old warning is no longer active", warning_row["active"] is False,
          "it used to look identical to a live one")
    check("and it now carries an end time", warning_row["ended_at"] is not None)
    check("the all-clear is never itself 'active'", clear_row["active"] is False)
    check("the all-clear names the place",
          "Stadium north concourse" in clear_row["title"], clear_row["title"])

    print("\n-- closing twice must not tell anyone twice -----------------------")
    again = warnings.all_clear(db, row.id, ZONE)
    check("nobody is told a second time", again["sent"] == 0,
          f"{again}")
    check("still only two messages", len(warnings.inbox(db, me)) == 2)

    print("\n-- the same place must not nag, but must still warn later ---------")
    # A draining crowd rises and falls, raising several genuine alarms within a
    # few minutes. The person should hear about the place once, not once per
    # wave - but a fresh danger hours later must still reach them.
    row2 = incidents.open_incident(db, RECORD)
    again = warnings.warn_people_near(db, registry, RECORD, incident_id=row2.id)
    check("a second alarm minutes later does NOT nag", again["sent"] == 0,
          "the inbox filled with avoid / clear / avoid / clear before this")

    # Wind every existing message back beyond the quiet period.
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=warnings.QUIET_MINUTES * 3)
    for r in db.query(alert_delivery).all():
        r.sent_at = cutoff
    db.commit()

    row3 = incidents.open_incident(db, RECORD)
    later = warnings.warn_people_near(db, registry, RECORD, incident_id=row3.id)
    check("but a fresh danger later does warn again", later["sent"] == 2,
          "silence must be temporary, never permanent")

    box = warnings.inbox(db, me)
    live = [w for w in box if w["active"]]
    check("exactly one live warning now", len(live) == 1, f"{len(box)} messages total")

    db.close()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAILED: {name} {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(run())
