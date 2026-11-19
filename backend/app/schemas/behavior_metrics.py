"""Схемы поведенческих метрик.

Формат запроса — как в уроке (Swagger покажет именно его):
    {"application_id": 0, "time_on_page": 0, "buttons_clicked": "string",
     "cursor_positions": "string", "return_frequency": 0}
плюс необязательные session_id, viewport_w, viewport_h, page (и doc_w, doc_h).

buttons_clicked и cursor_positions принимаются строкой с JSON (как в уроке),
а также готовым объектом/массивом. Строка, которая не парсится, сохраняется как {"raw": ...}.
"""
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CURSOR_POINTS = 3600  # час на странице при одной точке в секунду
MAX_BUTTONS = 200


def _parse_json(v: Any) -> Any:
    if isinstance(v, str):
        s = v.strip()
        if not s or s == "string":  # «string» — значение по умолчанию из Swagger
            return None
        try:
            return json.loads(s)
        except ValueError:
            return {"raw": s[:2000]}
    return v


def _clamp01(v: float) -> float:
    return round(min(1.0, max(0.0, v)), 4)


class BehaviorMetricsIn(BaseModel):
    application_id: int | None = Field(default=0, description="Принимается, но не проверяется (метрики анонимные)")
    time_on_page: int = Field(default=0, ge=0, le=86_400, description="секунд на странице")
    buttons_clicked: Any = Field(default="{}", description='JSON-строка: {"submit": 1, "service": 3}')
    cursor_positions: Any = Field(default="[]", description='JSON-строка: [{"x": 0.41, "y": 0.37}, ...] или [[x, y], ...]')
    return_frequency: int = Field(default=0, ge=0, le=10_000)
    session_id: str | None = Field(default=None, max_length=64)
    viewport_w: int | None = Field(default=None, ge=0, le=20_000)
    viewport_h: int | None = Field(default=None, ge=0, le=20_000)
    doc_w: int | None = Field(default=None, ge=0, le=50_000, description="ширина документа, px")
    doc_h: int | None = Field(default=None, ge=0, le=200_000, description="высота документа, px")
    page: str | None = Field(default=None, max_length=200)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "application_id": 0,
                "time_on_page": 0,
                "buttons_clicked": "string",
                "cursor_positions": "string",
                "return_frequency": 0,
            }
        }
    )

    @field_validator("session_id", "page", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("buttons_clicked", mode="before")
    @classmethod
    def _buttons(cls, v: Any) -> dict:
        v = _parse_json(v)
        if v is None:
            return {}
        if isinstance(v, list):  # ["submit", "service", "submit"] → {"submit": 2, "service": 1}
            counts: dict[str, int] = {}
            for name in v[:5000]:
                key = str(name)[:100]
                counts[key] = counts.get(key, 0) + 1
            return dict(list(counts.items())[:MAX_BUTTONS])
        if isinstance(v, dict):
            if "raw" in v and len(v) == 1:
                return v
            out = {}
            for k, n in list(v.items())[:MAX_BUTTONS]:
                try:
                    out[str(k)[:100]] = max(0, int(n))
                except (TypeError, ValueError):
                    continue
            return out
        return {"raw": str(v)[:2000]}

    @field_validator("cursor_positions", mode="before")
    @classmethod
    def _cursor(cls, v: Any) -> Any:
        v = _parse_json(v)
        if v is None:
            return []
        if isinstance(v, dict) and "raw" in v:
            return v
        if not isinstance(v, list):
            return {"raw": str(v)[:2000]}
        points = []
        for p in v[-MAX_CURSOR_POINTS:]:
            if isinstance(p, dict) and "x" in p and "y" in p:
                x, y = p.get("x"), p.get("y")
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                x, y = p[0], p[1]
            else:
                continue
            try:
                points.append({"x": float(x), "y": float(y)})
            except (TypeError, ValueError):
                continue
        return points

    @model_validator(mode="after")
    def _normalize_cursor(self):
        """Координаты → доли 0..1 от ширины и высоты документа.

        Если пришли пиксели (что-то больше 1) — делим на doc_w/doc_h, а без них на viewport.
        Уже нормализованные точки просто ограничиваем отрезком [0, 1].
        """
        # 0 из формата урока = «заявки нет»
        if self.application_id == 0:
            self.application_id = None
        pts = self.cursor_positions
        if not isinstance(pts, list) or not pts:
            return self
        in_pixels = any(p["x"] > 1 or p["y"] > 1 for p in pts)
        w = self.doc_w or self.viewport_w
        h = self.doc_h or self.viewport_h
        if in_pixels and w and h:
            self.cursor_positions = [{"x": _clamp01(p["x"] / w), "y": _clamp01(p["y"] / h)} for p in pts]
        elif in_pixels:
            # Пиксели без размеров нормализовать нечем — для heatmap такие точки бесполезны
            self.cursor_positions = []
        else:
            self.cursor_positions = [{"x": _clamp01(p["x"]), "y": _clamp01(p["y"])} for p in pts]
        return self


class BehaviorMetricsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str | None
    application_id: int | None
    time_on_page: int
    buttons_clicked: dict[str, Any]
    cursor_positions: Any
    return_frequency: int
    viewport_w: int | None
    viewport_h: int | None
    doc_w: int | None
    doc_h: int | None
    page: str | None
    created_at: datetime
    updated_at: datetime


class PeriodStats(BaseModel):
    avg_sec: float
    max_sec: int
    sessions: int


class HeatCell(BaseModel):
    x: float
    y: float
    count: int


class ButtonCount(BaseModel):
    name: str
    count: int


class BehaviorStats(BaseModel):
    periods: dict[str, PeriodStats]
    heatmap: list[HeatCell]
    top_buttons: list[ButtonCount]
    grid: int
    page_aspect: float
    total_sessions: int
    generated_at: datetime
