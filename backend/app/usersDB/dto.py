from pydantic import BaseModel
from typing import Literal


class user_dto(BaseModel):

    username: str
    password: str
    email: str
    number: str
    user_type: Literal["normal", "admin", "authority"]
