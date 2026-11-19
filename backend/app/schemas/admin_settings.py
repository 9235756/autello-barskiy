"""Pydantic-схемы услуг.

Out-схемы описывают id как int и даты как datetime — ровно те типы, что лежат в модели.
Ошибка из урока «Input should be a valid string» возникает, когда в схеме ответа
id/created_at объявлены как str: Pydantic 2 не приводит int/datetime к строке сам.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _short(n: int) -> str:
    """15000 → «15к», 1500000 → «1.5м» — для подписи диапазона."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:g}м"
    if n >= 1000:
        return f"{n / 1000:g}к"
    return str(n)


class AdminSettingsCreate(BaseModel):
    services: str = Field(min_length=2, max_length=200, examples=["Полировка кузова"])
    budget_min: int = Field(ge=0, le=100_000_000, examples=[15000])
    budget_max: int = Field(ge=0, le=100_000_000, examples=[60000])
    # Если не прислали — соберём из min/max: «15к–60к»
    budget_range: str | None = Field(default=None, max_length=50, examples=["15к–60к"])
    is_active: bool = True

    @model_validator(mode="after")
    def _check_range(self):
        self.services = self.services.strip()
        if self.budget_min > self.budget_max:
            raise ValueError("budget_min не может быть больше budget_max")
        if not self.budget_range:
            self.budget_range = f"{_short(self.budget_min)}–{_short(self.budget_max)}"
        return self


class AdminSettingsUpdate(BaseModel):
    """PUT: можно прислать только изменённые поля."""

    services: str | None = Field(default=None, min_length=2, max_length=200)
    budget_min: int | None = Field(default=None, ge=0, le=100_000_000)
    budget_max: int | None = Field(default=None, ge=0, le=100_000_000)
    budget_range: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class AdminSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    services: str
    budget_range: str
    budget_min: int
    budget_max: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
