from app.usersDB import models
from sqlalchemy.orm import Session

from app.usersDB.schemas import normal_userCreate, admin_userCreate, authority_userCreate
from app.usersDB.models import normal_user, admin_user, authority_user
from typing import Literal
from app.auth.security import hash_password, verify_password


def __create_normal_user(db: Session, userdata: normal_userCreate):
    userdata.password = hash_password(userdata.password)

    normal_user_instance = normal_user(**userdata.model_dump())
    db.add(normal_user_instance)
    db.commit()
    db.refresh(normal_user_instance)
    return normal_user_instance


def __create_admin_user(db: Session, userdata: admin_userCreate):
    userdata.password = hash_password(userdata.password)

    admin_user_instance = admin_user(**userdata.model_dump())
    db.add(admin_user_instance)
    db.commit()
    db.refresh(admin_user_instance)
    return admin_user_instance


def __create_authority_user(db: Session, userdata: authority_userCreate):
    userdata.password = hash_password(userdata.password)

    authority_user_instance = authority_user(**userdata.model_dump())
    db.add(authority_user_instance)
    db.commit()
    db.refresh(authority_user_instance)
    return authority_user_instance


def __verify_normal_user(db: Session, userdata: normal_userCreate):
    """
    Find the account by email, then check the password and RETURN THAT ANSWER.

    The previous version indexed .first() as if it were a tuple, which raised
    TypeError on every attempt, and it discarded the result of the password
    check - so once that crash was fixed, any password would have been accepted
    for any email on file.
    """
    user = db.query(normal_user).where(normal_user.email == userdata.email).first()
    if user is None:
        return None
    if not verify_password(userdata.password, str(user.password)):
        return None
    return user


def __verify_admin_user(db: Session, userdata: admin_userCreate):
    """
    Find the account by email, then check the password and RETURN THAT ANSWER.

    The previous version indexed .first() as if it were a tuple, which raised
    TypeError on every attempt, and it discarded the result of the password
    check - so once that crash was fixed, any password would have been accepted
    for any email on file.
    """
    user = db.query(admin_user).where(admin_user.email == userdata.email).first()
    if user is None:
        return None
    if not verify_password(userdata.password, str(user.password)):
        return None
    return user


def __verify_authority_user(db: Session, userdata: authority_userCreate):
    """
    Find the account by email, then check the password and RETURN THAT ANSWER.

    The previous version indexed .first() as if it were a tuple, which raised
    TypeError on every attempt, and it discarded the result of the password
    check - so once that crash was fixed, any password would have been accepted
    for any email on file.
    """
    user = db.query(authority_user).where(authority_user.email == userdata.email).first()
    if user is None:
        return None
    if not verify_password(userdata.password, str(user.password)):
        return None
    return user


def verify_user(
    db: Session, userdata: dict, user_role: Literal["normal", "admin", "authority"]
):
    """Returns the user row on success, None on failure. Falsy means refused."""
    if user_role == "normal":
        return __verify_normal_user(db, userdata=normal_userCreate(**userdata))
    elif user_role == "admin":
        return __verify_admin_user(db, userdata=admin_userCreate(**userdata))
    elif user_role == "authority":
        return __verify_authority_user(db, userdata=authority_userCreate(**userdata))


def create_user(
    db: Session, userdata: dict, user_role: Literal["normal", "admin", "authority"]
):
    if user_role == "normal":
        return __create_normal_user(db, userdata=normal_userCreate(**userdata))
    elif user_role == "admin":
        return __create_admin_user(db, userdata=admin_userCreate(**userdata))
    elif user_role == "authority":
        return __create_authority_user(db, userdata=authority_userCreate(**userdata))


def signin_existing_mail(db: Session, email: str):
    normal_query = db.query(normal_user).where(normal_user.email == email).first()
    admin_query = db.query(admin_user).where(admin_user.email == email).first()
    authority_query = (
        db.query(authority_user).where(authority_user.email == email).first()
    )

    if normal_query or admin_query or authority_query:
        return True
    return False


    return bcrypt.checkpw(password=password.encode(), hashed_password=hash)
