from app.usersDB.db import base
from sqlalchemy import String, Column
from sqlalchemy import UUID
from sqlalchemy.orm import validates
import uuid
import re


class normal_user(base):
    __tablename__ = "normal_users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(80), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    email = Column(String(120), nullable=False)
    number = Column(String(30), nullable=False)

    @validates("email")
    def validate_email(self, key, value):
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not bool(re.fullmatch(pattern=pattern, string=value)):
            raise ValueError("Error: Email is not in correct format")
        return value


class admin_user(base):
    __tablename__ = "admin_users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(80), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    email = Column(String(120), nullable=False)

    @validates("email")
    def validate_email(self, key, value):
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not bool(re.fullmatch(pattern=pattern, string=value)):
            raise ValueError("Error: Email is not in correct format")
        return value


class authority_user(base):
    __tablename__ = "authority_users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(80), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    email = Column(String(120), nullable=False)

    @validates("email")
    def validate_email(self, key, value):
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not bool(re.fullmatch(pattern=pattern, string=value)):
            raise ValueError("Error: Email is not in correct format")
        return value


# ---------------------------------------------------------------------------
# Crowd-safety tables
# ---------------------------------------------------------------------------
# Added so the detection engine survives a restart. Until now the engine held
# which phones it was watching in memory only, so every restart forgot every
# enrolled person and the system silently monitored nobody.

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text
from datetime import datetime, timezone


class device_consent(base):
    """
    A person's permission to be monitored, and the record of them taking it back.

    Nokia does not require consent in the sandbox, but nothing may be enrolled
    without a row here anyway. Location data about a named person is the whole
    legal weight of this product, and a consent table that only appears at
    production time is a consent table nobody designed.
    """

    __tablename__ = "device_consent"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String(30), nullable=False, unique=True)
    # Everything outside this table refers to the device by hash only.
    hashed_id = Column(String(32), nullable=False, unique=True, index=True)
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    # What they agreed to: "safety_monitoring" today, room for more later.
    scope = Column(String(60), nullable=False, default="safety_monitoring")

    @property
    def active(self) -> bool:
        return self.revoked_at is None

    @validates("phone_number")
    def validate_phone(self, key, value):
        if not re.fullmatch(r"^\+?[0-9]{5,15}$", value or ""):
            raise ValueError("Error: phone number must be 5-15 digits, optionally starting with +")
        return value


class monitored_device(base):
    """
    A device the engine is currently watching, and in which role.

    SENTINEL devices carry congestion subscriptions and district geofences.
    They are deliberately unbalanced, since more are enrolled where an event is
    expected, which makes them good at locating a crowd and biased at counting
    one.

    PANEL devices are a uniform random sample of all app users. Too thin to
    locate anything, but their share of the population is known exactly, so the
    fraction of the panel inside a zone is an unbiased estimate of the fraction
    of the city inside it. Only the panel is ever used for headcounts.
    """

    __tablename__ = "monitored_devices"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hashed_id = Column(String(32), nullable=False, unique=True, index=True)
    role = Column(String(20), nullable=False, default="sentinel")   # sentinel | panel
    district_id = Column(String(60), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    enrolled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class subscription_record(base):
    """
    Every live CAMARA subscription, so they can be torn down after a restart.

    Without this the system leaks: a restart forgets the subscription ids, the
    subscriptions stay alive at the operator, and they keep being billed with
    nothing listening to them.
    """

    __tablename__ = "subscription_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(String(120), nullable=False, unique=True, index=True)
    hashed_id = Column(String(32), nullable=False, index=True)
    kind = Column(String(20), nullable=False)      # congestion | district | zone
    area_id = Column(String(60), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    alive = Column(Boolean, nullable=False, default=True)


class incident(base):
    """A recorded alarm, kept so baselines can be built from real history."""

    __tablename__ = "incidents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id = Column(String(60), nullable=False, index=True)
    segment_id = Column(String(60), nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)
    people_low = Column(Integer, nullable=True)
    people_high = Column(Integer, nullable=True)
    pinch_density = Column(Float, nullable=True)
    fired_by = Column(String(40), nullable=True)
    reason = Column(Text, nullable=True)

    # Who took responsibility, and what they did about it.
    #
    # An alarm nobody answered and an alarm somebody answered look identical
    # without these. After an incident the first question asked is who knew and
    # when, and the second is what was done, so both are recorded rather than
    # reconstructed from memory afterwards.
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(80), nullable=True)
    closed_by = Column(String(80), nullable=True)
    action_taken = Column(Text, nullable=True)


class alert_delivery(base):
    """
    One warning sent to one person, and whether they have seen it.

    A row per recipient rather than a row per alarm, because the questions that
    matter afterwards are per person: was this individual warned, when, and did
    the warning reach them. An incident row cannot answer that.

    The recipient is stored by hash. A warning history that holds phone numbers
    would undo the vault, which is the one place a number is allowed to exist.
    """

    __tablename__ = "alert_deliveries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hashed_id = Column(String(32), nullable=False, index=True)
    zone_id = Column(String(60), nullable=False, index=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    # How it went out. "in_app" is the only channel wired up; the column exists
    # so adding SMS or push later does not need a migration of live rows.
    channel = Column(String(20), nullable=False, default="in_app")
    title = Column(String(160), nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    read_at = Column(DateTime(timezone=True), nullable=True)
    # Set when a transport reported failure, so undelivered warnings are visible
    # rather than being assumed to have arrived.
    failed_reason = Column(String(200), nullable=True)


class operator_zone(base):
    """
    A watch zone an operator drew, rather than one from the city plan.

    Stored so it survives a restart. Without this an operator would redraw
    their gates every time the service was restarted, and during an event that
    is exactly when nobody has time to.

    Width and length are required, not optional. The danger rule starts from
    the narrowest link - capacity is width x 72, and the area people are packed
    into is width x length - so a circle with no link cannot be judged at all.
    """

    __tablename__ = "operator_zones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id = Column(String(60), nullable=False, unique=True, index=True)
    label = Column(String(120), nullable=False)
    district_id = Column(String(60), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    radius_m = Column(Float, nullable=False)
    width_m = Column(Float, nullable=False)
    length_m = Column(Float, nullable=False)
    risk = Column(Float, nullable=False, default=1.3)
    created_by = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    active = Column(Boolean, nullable=False, default=True)


class push_token(base):
    """
    Where a person's phone can be reached.

    A push token is an address the phone's operating system hands out, and it
    only exists on a real installed app - a browser has none to give. One row
    per device rather than per person, because someone may carry a phone and a
    tablet and a warning that reaches only one of them is a warning that may
    reach neither.

    Stored against the hash, like everything else outside the vault. A push
    token is not a phone number, but it is still a way to reach a named person,
    so it is treated with the same care.

    Tokens expire and are reissued. The same device re-registering replaces its
    row rather than adding one, otherwise a person accumulates dead addresses
    and every alarm is sent to all of them.
    """

    __tablename__ = "push_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hashed_id = Column(String(32), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True)
    platform = Column(String(20), nullable=True)      # ios | android | web
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Set when the push service says the address is dead, so it is not tried
    # again and the operator can see coverage honestly.
    invalid_reason = Column(String(200), nullable=True)


class priority_session(base):
    """
    A network priority session opened for a responder during an incident.

    Recorded for the same reason subscriptions are: a session is billed for as
    long as it lives, and a restart that forgets the session ids leaves them
    running at the operator with nothing able to close them.

    Tied to the incident rather than to a person, because that is what decides
    when it ends. The incident closing is the signal to hand the priority back.
    """

    __tablename__ = "priority_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(120), nullable=False, unique=True, index=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    zone_id = Column(String(60), nullable=True)
    # The responder's device. Not a citizen's, so it is kept as given rather
    # than hashed: this is a work phone acting in an official role, and an
    # operator needs to see which responder holds priority.
    device = Column(String(60), nullable=False)
    profile = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="REQUESTED")
    status_info = Column(String(60), nullable=True)
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String(200), nullable=True)
