

from datetime import datetime

from pydantic import BaseModel, Field


class RoleOut(BaseModel):
    id: int
    code: str
    name: str


class UserOut(BaseModel):
    id: int
    username: str
    real_name: str | None
    email: str | None
    phone: str | None
    status: str
    skills: list[str] | None
    roles: list[str] = []
    created_at: datetime


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    real_name: str | None = None
    email: str | None = None
    phone: str | None = None
    role_codes: list[str] = []
    skills: list[str] = []


class RolesIn(BaseModel):
    role_codes: list[str]
