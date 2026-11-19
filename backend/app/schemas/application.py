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
    role: Literal["сотрудник", "руководитель", "собственник"] = Field(examples=["руководитель"])
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
    """Тело POST /api/applications.

    session_id — номер визита из behavior-metrics.js: backend проставит этому визиту номер заявки.
    metrics — формат части 2, необязателен (оставлен для совместимости со скриптами).
    """

    application: ApplicationIn
    metrics: MetricsIn | None = None
    session_id: str | None = Field(default=None, max_length=64)


class ApplicationCreated(BaseModel):
    id: int
    message: str = "Заявка отправлена!"


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


class LeadScoreOut(BaseModel):
    """Результат app/services/lead_scoring.py."""

    score: int = Field(ge=0, le=100)
    temperature: Literal["hot", "warm", "cold"]
    temperature_label: str
    urgency: str
    needs_personal_manager: bool
    department: str
    recommended_action: str
    reasons: list[str]
    breakdown: dict[str, int]
    engine: str
    ai_summary: str | None = None


class ApplicationRanked(ApplicationOut):
    """Заявка + оценка (для списка по приоритету и для «Просмотр»)."""

    scoring: LeadScoreOut


class SessionMetricsOut(BaseModel):
    """Метрики визита, из которого отправлена заявка (если найден)."""

    model_config = ConfigDict(from_attributes=True)

    time_on_page: int
    buttons_clicked: dict[str, Any]
    return_frequency: int
    extra: dict[str, Any]
    updated_at: datetime


class ApplicationDetail(ApplicationRanked):
    metrics: SessionMetricsOut | None = None


class ApplicationsSummary(BaseModel):
    total: int
    by_temperature: dict[str, int]
    by_service: list[dict[str, Any]]
    avg_budget: int | None
    last_7_days: int
    last_30_days: int
    needs_personal_manager: int
    avg_score: float
