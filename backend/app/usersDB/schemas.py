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


# These two used to extend normal_userBase, which carries a phone number. The
# admin and authority tables have no number column, so creating either account
# raised "'number' is an invalid keyword argument" and no operator or authority
# account could ever be made. They extend their own base now.
class admin_userCreate(admin_userBase):
    pass


class authority_userCreate(authority_userBase):
    pass
