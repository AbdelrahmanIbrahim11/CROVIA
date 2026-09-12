"""
The bridge between the user database and the detection engine.

Until now these were two separate systems: the database knew who the users
were, and the engine kept its watched phones in memory. A restart forgot
everyone, so the engine would come back up monitoring nobody while appearing to
work perfectly.

Nothing is monitored without an active consent row. Nokia does not require
consent in the sandbox, but a device is not enrolled here on that basis: the
whole legal weight of this product is that it holds location data about named
people, and permission that is only wired up at production time is permission
nobody actually designed.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.registry import DeviceRegistry, hash_phone
from app.usersDB.models import device_consent, monitored_device, normal_user

SENTINEL, PANEL = "sentinel", "panel"


def grant_consent(db: Session, phone: str, scope: str = "safety_monitoring") -> device_consent:
    """Record permission. Re-granting after a revocation reactivates the row."""
    row = db.query(device_consent).filter(device_consent.phone_number == phone).one_or_none()
    if row is None:
        row = device_consent(phone_number=phone, hashed_id=hash_phone(phone), scope=scope)
        db.add(row)
    else:
        row.revoked_at = None
        row.scope = scope
    db.commit()
    db.refresh(row)
    return row


def revoke_consent(db: Session, phone: str) -> bool:
    """
    Withdraw permission and stop monitoring immediately.

    Deactivating the device in the same transaction matters: a consent row that
    says "no" while the engine keeps watching is worse than never having asked.
    """
    row = db.query(device_consent).filter(device_consent.phone_number == phone).one_or_none()
    if row is None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    dev = db.query(monitored_device).filter(
        monitored_device.hashed_id == row.hashed_id).one_or_none()
    if dev:
        dev.active = False
    db.commit()
    return True


def enrol(db: Session, phone: str, role: str = SENTINEL,
          district_id: str | None = None) -> monitored_device | None:
    """Start watching a device. Refuses without active consent."""
    consent = db.query(device_consent).filter(
        device_consent.phone_number == phone).one_or_none()
    if consent is None or consent.revoked_at is not None:
        return None

    dev = db.query(monitored_device).filter(
        monitored_device.hashed_id == consent.hashed_id).one_or_none()
    if dev is None:
        dev = monitored_device(hashed_id=consent.hashed_id, role=role,
                               district_id=district_id, active=True)
        db.add(dev)
    else:
        dev.role = role
        dev.active = True
        if district_id:
            dev.district_id = district_id
    db.commit()
    db.refresh(dev)
    return dev


def auto_enrol_users(db: Session, panel_size: int = 400,
                     pool_size: int = 500, seed: int = 7,
                     **_ignored) -> dict:
    """
    Turn consenting users into a sentinel pool and a citywide panel.

    NO DISTRICT IS ASSIGNED HERE, and that is the point of this version.

    The previous one dealt the remaining users into four piles by position in a
    shuffled list - the first sixty became "stadium", the next sixty
    "foxhills", and so on. Nothing had checked whether any of them were
    anywhere near those places. That guess was then written down and treated as
    fact by everything downstream: congestion notifications were attributed to
    it, and the share that decides which district deserves paid attention was
    computed from it.

    Now the network decides. Every sentinel is subscribed to all four district
    circles and reports which one it is really in, so the district lists are
    observed rather than invented.

    The two groups still differ on purpose. The panel is a uniform random
    sample used for counting, and its share of the population has to be known
    exactly for the headcount to be unbiased. The sentinel pool carries the
    congestion and geofence subscriptions. Using one group for both jobs
    under-counts an event crowd by two to three times.

    `pool_size` is how many sentinels to carry. It has to be large enough that
    the emptiest district still holds enough phones to be trusted - see
    MIN_FLEET in the engine - because people are not spread evenly across a
    city and we no longer get to pretend they are.
    """
    rng = random.Random(seed)

    rows = (db.query(device_consent, normal_user)
            .join(normal_user, normal_user.number == device_consent.phone_number)
            .filter(device_consent.revoked_at.is_(None))
            .all())
    if not rows:
        return {"sentinels": 0, "panel": 0, "consenting": 0}

    people = [(c.phone_number, u) for c, u in rows]
    rng.shuffle(people)

    panel_take = min(panel_size, len(people))
    panel = people[:panel_take]
    rest = people[panel_take:]

    for phone, _ in panel:
        enrol(db, phone, PANEL)

    # Sentinels get no district. The geofences placed in subscribe_device are
    # what put them somewhere, once the network has answered.
    sentinels = rest[:pool_size]
    for phone, _ in sentinels:
        enrol(db, phone, SENTINEL)

    return {"sentinels": len(sentinels), "panel": len(panel),
            "consenting": len(people)}


def load_into_registry(db: Session, registry: DeviceRegistry) -> dict:
    """
    Rebuild the engine's in-memory view from the database at startup.

    The vault is filled from the consent table, because that is the only place
    a real phone number is held. Everything else refers to the device by hash.
    """
    consents = {c.hashed_id: c.phone_number for c in
                db.query(device_consent).filter(device_consent.revoked_at.is_(None)).all()}
    devices = db.query(monitored_device).filter(monitored_device.active.is_(True)).all()

    n_sent = n_panel = 0
    for dev in devices:
        phone = consents.get(dev.hashed_id)
        if not phone:
            continue  # consent withdrawn: do not monitor, whatever the device row says
        if dev.role == PANEL:
            registry.add_panel(phone, dev.district_id)
            n_panel += 1
        else:
            registry.add_sentinel(phone, dev.district_id)
            n_sent += 1
    return {"sentinels": n_sent, "panel": n_panel, "consenting": len(consents)}


def subscribe_device(db: Session, engine, phone: str,
                     _district_id: str | None = None) -> dict:
    """
    Create the CAMARA subscriptions for one device and remember their ids.

    Five subscriptions per device:

      CONGESTION  the always-on signal. Its payload carries no location and no
                  device id, so on its own it can only say that something is
                  happening somewhere.

      DISTRICT    a geofence on EVERY district circle, each with initial_event
                  set. These are what give congestion an address. The network
                  answers immediately for the one circle the phone is inside
                  and says nothing about the rest, so the device places itself.

    The district argument is accepted and ignored. It used to select the single
    circle to watch, which meant the subscription could only ever confirm
    whichever district had been guessed for this phone - never contradict it.
    A wrong guess produced silence, and silence changed nothing, so the guess
    stood for ever.

    Subscription ids are written to the database because they are the only way
    to tear these down later. Forgetting them leaves the subscriptions alive at
    the operator, still billing, with nothing listening.
    """
    from app.camara.client import Area, ApiError
    from app.core.city import city
    from app.usersDB.models import subscription_record

    hashed = hash_phone(phone)
    # Each device gets its own webhook address, ending in its hash.
    #
    # A real congestion notification from the network names neither a device
    # nor a subscription - `source` turned out to be the event type, not a URL
    # with an id in it. The address it arrives at is therefore the only thing
    # that says who it is about. Sending every device to one shared path made
    # every notification unattributable.
    #
    # The hash is safe to put in a URL: it is not a phone number, and it is
    # already what every part of the system outside the vault uses.
    sink = f"{__import__('os').getenv('WEBHOOK_BASE_URL', 'http://localhost:8000')}/webhooks"
    made: list[str] = []

    try:
        sub = engine.client.create_congestion_subscription(
            phone, f"{sink}/congestion/{hashed}", 7 * 86400)
        engine.registry.bind_subscription(sub, hashed, "congestion", district_id or "")
        db.add(subscription_record(subscription_id=sub, hashed_id=hashed, kind="congestion"))
        made.append(sub)
    except Exception as exc:
        # Deliberately broad. The Nokia SDK raises its own exception types, not
        # ours, and letting one escape turned a partially successful enrolment
        # into a 500 that also discarded the subscription that HAD been
        # created - so the operator was billed for it and nothing recorded it.
        return {"error": f"congestion subscription failed: {type(exc).__name__}: {exc}"}

    # A geofence on EVERY district, not on one guessed district.
    #
    # Each subscription carries initial_event, so the network answers straight
    # away for the circle the phone is actually inside and stays silent for the
    # other three. That one answer places the device. Asking about all four is
    # what removes the need to know where it is beforehand - and a phone that
    # answers nowhere is left in no district, which is the truthful result
    # rather than a guess.
    #
    # Only area-entered is subscribed. Moving between districts is already
    # handled, because placing a device in a new district removes it from its
    # previous one. Subscribing to area-left as well would double the cost, as
    # CAMARA allows one event type per subscription.
    placed_in: str | None = None
    geo_failures: list[str] = []
    for did, d in city.districts.items():
        try:
            gsub, evt = engine.client.create_geofence_subscription(
                phone, did, Area(d.center.lat, d.center.lon, d.radius_m),
                f"{sink}/geofencing/{hashed}", 7 * 86400, initial_event=True)
            engine.registry.bind_subscription(gsub, hashed, "district", did)
            db.add(subscription_record(subscription_id=gsub, hashed_id=hashed,
                                       kind="district", area_id=did))
            made.append(gsub)
            # The built-in stand-in client answers inline; the real network
            # answers later on the webhook. Both paths end in the same place.
            if evt and evt.get("type") == "area-entered":
                engine.registry.place(hashed, did, engine.now)
                placed_in = did
        except Exception as exc:
            # Broad for the same reason as above: the Nokia SDK raises its own
            # exception types. One district failing must not discard the
            # subscriptions that already succeeded and are already billed.
            geo_failures.append(f"{did}: {type(exc).__name__}: {exc}")

    db.commit()
    out: dict = {"subscriptions": made, "placed_in": placed_in}
    if geo_failures:
        out["warning"] = "; ".join(geo_failures)[:400]
    return out
