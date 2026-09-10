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

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.auth.security import create_access_token
from app.services import enrollment
from app.usersDB import services as dbServices
from app.usersDB.db import getdb

logger = logging.getLogger("crovia.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

ROLES = ("normal", "admin", "authority")


class RegisterIn(BaseModel):
    username: str
    password: str
    email: EmailStr
    # Only a citizen account carries a phone number, because only a citizen is
    # ever monitored. An operator watches the city; they are not watched.
    number: str | None = None
    user_type: str = "normal"
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
    if body.user_type not in ROLES:
        raise HTTPException(status_code=422,
                            detail=f"user_type must be one of {', '.join(ROLES)}")
    if len(body.password) < 8:
        raise HTTPException(status_code=422,
                            detail="password must be at least 8 characters")
    if body.user_type == "normal" and not body.number:
        raise HTTPException(status_code=422,
                            detail="a citizen account needs a phone number")
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
        enrollment.grant_consent(db, body.number)
        monitored = True

    logger.info("registered a %s account (monitored=%s)", body.user_type, monitored)
    return {"username": str(user.username), "email": str(user.email),
            "role": body.user_type, "user_id": str(user.id),
            "monitored": monitored}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(getdb)):
    if body.user_type not in ROLES:
        raise HTTPException(status_code=422,
                            detail=f"user_type must be one of {', '.join(ROLES)}")

    user = dbServices.verify_user(
        db=db,
        userdata={"username": "", "password": body.password, "email": body.email,
                  **({"number": ""} if body.user_type == "normal" else {})},
        user_role=body.user_type,
    )
    if not user:
        # Same message either way, so this cannot be used to discover which
        # email addresses have accounts.
        raise HTTPException(status_code=401, detail="wrong email or password")

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
