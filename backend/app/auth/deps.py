"""
Who is calling, and what they are allowed to do.

Every protected route depends on one of these. They read the bearer token,
check the signature and the expiry, and hand back what it says.

The roles, and what each is for:

    normal      a person in the city. Sees warnings addressed to them and
                controls their own consent. Never sees the operations picture.

    admin       operations. Sees the live city, the zones, the spend, and can
                draw watch zones.

    authority   police, civil defence, the stadium safety officer. Everything
                admin can do, plus acknowledging and closing an incident, which
                is a record of who took responsibility for it.

Read as a ladder: authority can do anything admin can. That is deliberate - a
safety officer locked out of the map during an incident is a worse failure than
one who can see more than they strictly need.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.auth.security import decode_token

# Higher number means more power. Comparing numbers keeps the rule in one place
# instead of scattering role lists through the routes.
RANK = {"normal": 1, "admin": 2, "authority": 3}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """
    The signed-in caller, from the Authorization header.

    Refuses with 401 if the header is missing, malformed, expired or tampered
    with. The message never says which, because telling an attacker whether a
    token merely expired is free information.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="sign in first",
                            headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="your session has ended - sign in again",
                            headers={"WWW-Authenticate": "Bearer"})
    return payload


def require_role(minimum: str):
    """
    Build a dependency that demands at least this much authority.

    Used as: Depends(require_role("admin"))
    """
    needed = RANK[minimum]

    def check(user: dict = Depends(current_user)) -> dict:
        if RANK.get(user.get("role", ""), 0) < needed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"this needs a {minimum} account")
        return user

    return check


# Ready-made, so routes read as a sentence.
require_signed_in = current_user
require_operator = require_role("admin")
require_authority = require_role("authority")
