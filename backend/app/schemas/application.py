"""Pydantic-схемы заявки и поведенческих метрик.

Фронт присылает ОДИН пакет: {"application": {...}, "metrics": {...}}.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PHONE_RE = r"^\+?[0-9 ()\-]{10,20}$"
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ApplicationIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=100, examples=["Барский"])
    first_name: str = Field(min_length=1, max_length=100, examples=["Андрей"])
    middle_name: str | None = Field(default=None, max_length=100)
    phone: str = Field(pattern=PHONE_RE, examples=["+7 916 123-45-67"])
    email: str | None = Field(default=None, max_length=200)
    service_id: int = Field(gt=0, examples=[1])
    business_niche: str | None = Field(default=None, max_length=100, examples=["Детейлинг-центр"])
    company_size: str | None = Field(default=None, max_length=50)
    task_volume: str | None = Field(default=None, max_length=100)
    role: Literal["сотрудник", "руководитель"] = Field(examples=["руководитель"])
    need_volume: str | None = Field(default=None, max_length=100)
    deadline: str | None = Field(default=None, max_length=100)
    task_type: str | None = Field(default=None, max_length=100)
    product_interest: str | None = Field(default=None, max_length=100)
    budget: str | None = Field(default=None, max_length=50, examples=["120000"])
    contact_method: str | None = Field(default=None, max_length=30, examples=["telegram"])
    contact_time: str | None = Field(default=None, max_length=50)
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        # Пустые строки из формы превращаем в NULL
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        import re

        if v is not None and not re.match(EMAIL_RE, v):
            raise ValueError("некорректный email")
        return v

    @field_validator("budget", mode="before")
    @classmethod
    def _budget_to_str(cls, v: Any) -> Any:
        # Ползунок отдаёт число — храним строкой, как требует модель
        return str(v) if isinstance(v, (int, float)) else v


class Click(BaseModel):
    el: str = Field(max_length=100)
    t: float = Field(ge=0, description="секунда от открытия страницы")


class Hover(BaseModel):
    el: str = Field(max_length=100)
    ms: int = Field(ge=0, description="длительность наведения, мс")


class MetricsIn(BaseModel):
    time_on_page_sec: int = Field(default=0, ge=0, le=86_400)
    clicks: list[Click] = Field(default_factory=list, max_length=300)
    hovers: list[Hover] = Field(default_factory=list, max_length=300)
    return_count: int = Field(default=0, ge=0, le=1000)
    scroll_depth: int = Field(default=0, ge=0, le=100)
    utm: dict[str, str] = Field(default_factory=dict)
    referrer: str | None = Field(default=None, max_length=2000)
    user_agent: str | None = Field(default=None, max_length=1000)
    screen: str | None = Field(default=None, max_length=30)
    language: str | None = Field(default=None, max_length=20)


class ApplicationPacket(BaseModel):
    """Тело POST /api/applications."""

    application: ApplicationIn
    metrics: MetricsIn = Field(default_factory=MetricsIn)


class ApplicationCreated(BaseModel):
    id: int
    message: str = "Заявка отправлена!"


class MetricsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application_id: int
    time_on_page_sec: int
    clicks: list[dict[str, Any]]
    hovers: list[dict[str, Any]]
    return_count: int
    scroll_depth: int
    utm: dict[str, Any]
    referrer: str | None
    user_agent: str | None
    screen: str | None
    language: str | None
    created_at: datetime


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_name: str
    first_name: str
    middle_name: str | None
    phone: str
    email: str | None
    service_id: int | None
    service_name: str | None
    business_niche: str | None
    company_size: str | None
    task_volume: str | None
    role: str
    need_volume: str | None
    deadline: str | None
    task_type: str | None
    product_interest: str | None
    budget: str | None
    contact_method: str | None
    contact_time: str | None
    comment: str | None
    created_at: datetime
    metrics: MetricsOut | None = None
