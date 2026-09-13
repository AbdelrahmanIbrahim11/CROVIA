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
# Two roles, not three.
#
# There used to be a separate "admin" sitting between the public and the
# emergency services, and in practice nobody could say what it was for that
# authority did not already cover - so it was one more account type to issue,
# secure and explain, guarding exactly the same screens. Removing it means one
# fewer way to get the permissions wrong.
#
# Any admin accounts already in the database simply stop being able to sign in.
# Their rows are left alone rather than deleted, because destroying account
# history to tidy up a role is not a trade worth making.
RANK = {"normal": 1, "authority": 2}


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
                detail=f"this needs {'an' if minimum[0] in 'aeiou' else 'a'} "
                       f"{minimum} account")
        return user

    return check


# Ready-made, so routes read as a sentence.
require_signed_in = current_user
# The operations screens - live headcounts, spend, incidents, drawn zones - now
# belong to the authority. The name is kept because fifteen routes read as
# "Depends(require_operator)" and that still describes who they are for: the
# person operating the system, rather than a member of the public.
require_operator = require_role("authority")
require_authority = require_role("authority")


def phone_of(db, user: dict) -> str | None:
    """
    The caller's own phone number, looked up from their account.

    Needed because a person's warnings and their consent are keyed by a hash of
    their number, while a token identifies them by account id. Without this the
    only way to offer "my warnings" would be to let the caller name the hash,
    and a caller who can name any hash can read anyone's warnings.

    Only citizen accounts have a number. Operators are not monitored.
    """
    import uuid

    from app.usersDB.models import normal_user

    if user.get("role") != "normal":
        return None
    try:
        # The id column holds a real UUID, so the string carried in the token
        # has to be converted first. Comparing the column to plain text makes
        # SQLAlchemy reach for .hex on a str and raise.
        user_id = uuid.UUID(str(user.get("sub")))
    except (ValueError, TypeError):
        return None
    row = db.query(normal_user).filter(normal_user.id == user_id).one_or_none()
    return str(row.number) if row and row.number else None
