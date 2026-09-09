from db import base
from sqlalchemy import String, Column
from sqlalchemy import UUID
from sqlalchemy.orm import validates
import uuid
import re


class normal_user(base):
    __tablename__ = "normal_users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4())
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4())
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
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4())
    username = Column(String(80), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    email = Column(String(120), nullable=False)

    @validates("email")
    def validate_email(self, key, value):
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not bool(re.fullmatch(pattern=pattern, string=value)):
            raise ValueError("Error: Email is not in correct format")
        return value
