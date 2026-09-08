from pydantic import BaseModel, validators, EmailStr, Field


class normal_userBase(BaseModel):
    model_config = {"strict": True}
    username: str
    password: str
    email: EmailStr
    number: str


class admin_userBase(BaseModel):
    model_config = {"strict": True}
    username: str
    password: str
    email: EmailStr


class authority_userBase(BaseModel):
    model_config = {"strict": True}
    username: str
    password: str
    email: EmailStr


class normal_user(normal_userBase):
    id: str

    class config:
        orm_mode = True
        form_attribute = True


class admin_user(admin_userBase):
    id: str

    class config:
        orm_mode = True
        form_attribute = True


class authority_user(authority_userBase):
    id: str

    class config:
        orm_mode = True
        form_attribute = True


class normal_userCreate(normal_userBase):
    pass


class admin_userCreate(normal_userBase):
    pass


class authority_userCreate(normal_userBase):
    pass
