"""Схемы авторизации админки."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthCheck(BaseModel):
    has_admins: bool


class AdminRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.@-]+$", examples=["admin"])
    # bcrypt учитывает только 72 байта — длиннее не принимаем, чтобы не было «тихой» обрезки
    password: str = Field(min_length=8, max_length=72, examples=["change_me_demo"])

    @field_validator("password")
    @classmethod
    def _bytes_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("пароль длиннее 72 байт (ограничение bcrypt)")
        return v


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="секунд до истечения токена")
