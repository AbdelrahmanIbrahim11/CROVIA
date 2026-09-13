"""
Register, sign in, sign out.

Login used to return only a username and an email, which proved nothing on the
next request, so there was no way to protect anything. It now returns a signed
token that the app sends back on every call.

Three deliberate choices.

LOGIN NEEDS ONLY AN EMAIL AND A PASSWORD. The old normal-user lookup also
required the phone number to match, which is not something a person types to
sign in, and it made the account unreachable if the number was stored with a
different prefix.

THE SAME ANSWER FOR A WRONG EMAIL AND A WRONG PASSWORD. Saying "no such
account" tells a stranger which addresses are registered, which is exactly the
first thing someone probing the system wants.

SIGNING OUT IS HONEST ABOUT WHAT IT DOES. The token is stateless, so the server
cannot tear it up; the app forgets it. That is stated in the response rather
than implied, and it is why tokens expire in hours rather than months.
"""

from __future__ import annotations

import hmac
import logging
import re
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth import ratelimit
from app.auth.deps import current_user
from app.auth.security import create_access_token
from app.services import enrollment
from app.usersDB import services as dbServices
from app.usersDB.db import getdb

logger = logging.getLogger("crovia.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

ROLES = ("normal", "authority")


class RegisterIn(BaseModel):
    username: str
    password: str
    email: EmailStr
    # Only a citizen account carries a phone number, because only a citizen is
    # ever monitored. An operator watches the city; they are not watched.
    number: str | None = None
    user_type: str = "normal"
    # Required to create anything other than a citizen account. See below.
    invite_code: str | None = None
    # Whether the person agreed to be monitored, asked at the moment they sign
    # up rather than buried in settings afterwards. Defaults to False: silence
    # is not agreement, and an account created without an explicit yes is an
    # account CROVIA does not watch.
    consent: bool = False


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    user_type: str = "normal"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    username: str
    email: EmailStr
    user_id: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(getdb)):
    """
    Create an account.

    Anyone may create a CITIZEN account - that is the point of the product.

    An operator or authority account needs STAFF_INVITE_CODE, because those
    accounts can see the whole city, every alarm and every incident. Until this
    check existed, a stranger who found the address could simply ask for
    user_type "admin" and be given one, which was tested and confirmed. Nothing
    stopped them: the role came from the request body and was believed.

    The code lives in the environment rather than in a database table so that
    the very first operator account can be made at all - a rule that only
    existing staff may create staff has no way to start.
    """
    if body.user_type not in ROLES:
        raise HTTPException(status_code=422,
                            detail=f"user_type must be one of {', '.join(ROLES)}")

    if body.user_type != "normal":
        expected = os.getenv("STAFF_INVITE_CODE", "").strip()
        if not expected:
            raise HTTPException(
                status_code=403,
                detail="operator and authority accounts are not open for sign-up")
        if not body.invite_code or not hmac.compare_digest(body.invite_code, expected):
            # Constant time, so the code cannot be worked out one character at a
            # time by measuring how long the answer takes.
            raise HTTPException(status_code=403, detail="invalid invite code")
    if len(body.password) < 8:
        raise HTTPException(status_code=422,
                            detail="password must be at least 8 characters")
    # Checked against what the columns can actually hold.
    #
    # Without this a long name reached the database, the insert failed on the
    # column width, and the person got a 500 with no idea which field was the
    # problem. The limits below are the column widths, so the message can name
    # the field instead of the server falling over.
    if not body.username.strip():
        raise HTTPException(status_code=422, detail="please enter your name")
    if len(body.username) > 80:
        raise HTTPException(status_code=422,
                            detail="name must be 80 characters or fewer")
    if len(body.email) > 120:
        raise HTTPException(status_code=422,
                            detail="email must be 120 characters or fewer")
    if len(body.password) > 200:
        # bcrypt itself ignores anything past 72 bytes, so a longer password is
        # not more secure - it just cannot be stored.
        raise HTTPException(status_code=422,
                            detail="password must be 200 characters or fewer")
    if body.user_type == "normal":
        if not body.number:
            raise HTTPException(status_code=422,
                                detail="a citizen account needs a phone number")
        # Checked HERE, before anything is written.
        #
        # The consent table validates the same rule, but it did so after the
        # account row had already been created and committed. A short number
        # therefore produced an account with no consent attached, a 500 rather
        # than a readable message, and a person who could not sign up again
        # because their email was "already registered".
        if not re.fullmatch(r"^\+?[0-9]{5,15}$", body.number.replace(" ", "")):
            raise HTTPException(
                status_code=422,
                detail="phone number must be 5 to 15 digits, and may start "
                       "with + and the country code - for example +97430001234")
    if dbServices.signin_existing_mail(db=db, email=body.email):
        raise HTTPException(status_code=400, detail="that email is already registered")

    fields = {"username": body.username, "password": body.password, "email": body.email}
    # Only a citizen record has a phone number. Operators and authorities are
    # not monitored, so their tables have no such column.
    if body.user_type == "normal":
        fields["number"] = body.number

    user = dbServices.create_user(db=db, userdata=fields, user_role=body.user_type)
    if not user:
        raise HTTPException(status_code=400, detail="could not create the account")

    # A citizen who agreed is enrolled straight away, in the same request. Doing
    # it later would leave a window where an account exists, the person believes
    # they are protected, and nothing is watching them.
    monitored = False
    if body.user_type == "normal" and body.consent and body.number:
      try:
        enrollment.grant_consent(db, body.number)
        # Consent on its own watches nobody. It records permission; enrolling is
        # what puts the device on the list the engine reads at startup. Doing
        # only the first leaves a person who ticked the box, believes they are
        # protected, and is not on any list.
        #
        # They join the panel rather than the sentinel fleet. The panel is a
        # uniform sample used for counting, and it is the role a person who
        # simply signed up genuinely belongs to - sentinels are placed
        # deliberately where an event is expected.
        enrollment.enrol(db, body.number, enrollment.PANEL)
        monitored = True
      except Exception as exc:
        # The account exists and is usable; only the monitoring failed. Saying
        # so is better than a 500 that leaves the person unable to sign up
        # again because their email is taken by an account they never got.
        db.rollback()
        logger.warning("account created but monitoring could not start: %s", exc)

    logger.info("registered a %s account (monitored=%s)", body.user_type, monitored)
    return {"username": str(user.username), "email": str(user.email),
            "role": body.user_type, "user_id": str(user.id),
            "monitored": monitored}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(getdb)):
    if body.user_type not in ROLES:
        raise HTTPException(status_code=422,
                            detail=f"user_type must be one of {', '.join(ROLES)}")

    # Checked before the password, so a blocked attempt costs neither a bcrypt
    # comparison nor a database read - which is what stops the rate limiter
    # itself becoming the way to overload the service.
    address = request.client.host if request.client else "unknown"
    wait = ratelimit.check(body.email, address)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail=f"too many sign-in attempts - try again in {int(wait // 60) + 1} minutes",
            headers={"Retry-After": str(int(wait))})

    user = dbServices.verify_user(
        db=db,
        userdata={"username": "", "password": body.password, "email": body.email,
                  **({"number": ""} if body.user_type == "normal" else {})},
        user_role=body.user_type,
    )
    if not user:
        ratelimit.record_failure(body.email, address)
        # Same message either way, so this cannot be used to discover which
        # email addresses have accounts.
        raise HTTPException(status_code=401, detail="wrong email or password")

    ratelimit.clear(body.email, address)
    token, ttl = create_access_token(user_id=str(user.id), role=body.user_type,
                                     username=str(user.username), email=str(user.email))
    return TokenOut(access_token=token, expires_in=ttl, role=body.user_type,
                    username=str(user.username), email=str(user.email),
                    user_id=str(user.id))


@router.get("/me")
def me(user: dict = Depends(current_user)):
    """Who the token says you are. The app calls this to check it is still valid."""
    return {"user_id": user["sub"], "role": user["role"],
            "username": user["username"], "email": user["email"]}


@router.post("/logout")
def logout(user: dict = Depends(current_user)):
    """
    Sign out.

    The token is stateless, so the server cannot cancel it. The app deletes it,
    and it expires on its own within hours. Said plainly rather than pretending
    a session was destroyed.
    """
    logger.info("signed out a %s account", user.get("role"))
    return {"status": "signed out",
            "note": "the app deletes the token; it also expires on its own"}
