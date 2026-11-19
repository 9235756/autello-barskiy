"""Поведенческие метрики посетителей главной — АНОНИМНЫЕ, одна строка на визит.

Отличие от части 2: метрики больше не привязаны к заявке связью 1:1.
application_id принимается (формат урока), но не проверяется: без FK и без UNIQUE.
Поэтому ошибки «Behavior metrics for application 0 already exists» здесь не бывает.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base

# Сетка heatmap: 40×40 ячеек на всю высоту и ширину документа
HEATMAP_GRID = 40
PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}


class BehaviorMetrics(Base):
    """Снимок поведения посетителя за визит. Фронт шлёт накопленный снимок раз в секунду:
    с session_id строка обновляется (upsert), без него — каждый раз новая строка.

    SQL (тот же текст — в sql/schema_part3.sql):

        CREATE TABLE behavior_metrics (
            id                SERIAL PRIMARY KEY,
            session_id        VARCHAR(64) UNIQUE,          -- crypto.randomUUID() из браузера
            application_id    INTEGER,                     -- принимаем, НЕ проверяем: без FK и UNIQUE
            time_on_page      INTEGER NOT NULL DEFAULT 0,  -- секунд на странице (вкладка активна)
            buttons_clicked   JSONB   NOT NULL DEFAULT '{}',  -- {"submit": 1, "service": 3}
            cursor_positions  JSONB   NOT NULL DEFAULT '[]',  -- [{"x":0.41,"y":0.37}, ...] доли 0..1
            return_frequency  INTEGER NOT NULL DEFAULT 0,  -- сколько раз вернулся на вкладку
            viewport_w        INTEGER,
            viewport_h        INTEGER,
            doc_w             INTEGER,                     -- размер документа, к нему нормализован курсор
            doc_h             INTEGER,
            page              VARCHAR(200),
            extra             JSONB   NOT NULL DEFAULT '{}',  -- utm, referrer, user_agent (из заявки)
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_behavior_metrics_created_at ON behavior_metrics (created_at);
        CREATE INDEX ix_behavior_metrics_application_id ON behavior_metrics (application_id);
    """

    __tablename__ = "behavior_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    application_id: Mapped[int | None] = mapped_column(Integer, index=True)
    time_on_page: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    buttons_clicked: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    cursor_positions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    return_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    viewport_w: Mapped[int | None] = mapped_column(Integer)
    viewport_h: Mapped[int | None] = mapped_column(Integer)
    doc_w: Mapped[int | None] = mapped_column(Integer)
    doc_h: Mapped[int | None] = mapped_column(Integer)
    page: Mapped[str | None] = mapped_column(String(200))
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# Поля, которые можно перезаписать снимком
_SNAPSHOT_FIELDS = (
    "application_id", "time_on_page", "buttons_clicked", "cursor_positions", "return_frequency",
    "viewport_w", "viewport_h", "doc_w", "doc_h", "page",
)


class BehaviorMetricsCRUD:
    """Операции с метриками."""

    @staticmethod
    def create(db: Session, data: dict, commit: bool = True) -> BehaviorMetrics:
        obj = BehaviorMetrics(**data)
        db.add(obj)
        if commit:
            db.commit()
            db.refresh(obj)
        else:
            db.flush()
        return obj

    @staticmethod
    def upsert(db: Session, data: dict) -> BehaviorMetrics:
        """Есть session_id → INSERT ... ON CONFLICT (session_id) DO UPDATE; нет — обычная вставка.

        Снимок накопительный, поэтому старые значения просто перезаписываются.
        Пустой application_id (null/0) не затирает уже проставленный номер заявки.
        """
        if not data.get("session_id"):
            return BehaviorMetricsCRUD.create(db, data)
        stmt = insert(BehaviorMetrics).values(**data)
        update = {k: stmt.excluded[k] for k in _SNAPSHOT_FIELDS if k in data and k != "application_id"}
        update["application_id"] = func.coalesce(
            func.nullif(stmt.excluded.application_id, 0), BehaviorMetrics.application_id
        )
        update["updated_at"] = func.now()
        stmt = stmt.on_conflict_do_update(index_elements=["session_id"], set_=update).returning(BehaviorMetrics.id)
        new_id = db.execute(stmt).scalar_one()
        db.commit()
        obj = db.get(BehaviorMetrics, new_id)
        db.refresh(obj)
        return obj

    @staticmethod
    def attach_application(db: Session, session_id: str, application_id: int) -> bool:
        """Проставить номер заявки визиту, из которого её отправили (без commit)."""
        obj = db.scalars(select(BehaviorMetrics).where(BehaviorMetrics.session_id == session_id)).first()
        if obj is None:
            return False
        obj.application_id = application_id
        return True

    @staticmethod
    def get(db: Session, obj_id: int) -> BehaviorMetrics | None:
        return db.get(BehaviorMetrics, obj_id)

    @staticmethod
    def get_by_application(db: Session, application_id: int) -> BehaviorMetrics | None:
        stmt = (
            select(BehaviorMetrics)
            .where(BehaviorMetrics.application_id == application_id)
            .order_by(BehaviorMetrics.updated_at.desc())
        )
        return db.scalars(stmt).first()

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> list[BehaviorMetrics]:
        stmt = select(BehaviorMetrics).order_by(BehaviorMetrics.updated_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt))

    @staticmethod
    def count(db: Session) -> int:
        return db.scalar(select(func.count()).select_from(BehaviorMetrics)) or 0

    @staticmethod
    def update(db: Session, obj_id: int, data: dict) -> BehaviorMetrics | None:
        obj = db.get(BehaviorMetrics, obj_id)
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def delete(db: Session, obj_id: int) -> bool:
        obj = db.get(BehaviorMetrics, obj_id)
        if obj is None:
            return False
        db.delete(obj)
        db.commit()
        return True

    # ---------- Статистика для модального окна «Статистика пользователей» ----------

    @staticmethod
    def stats(db: Session) -> dict:
        now = datetime.now(timezone.utc)
        periods = {}
        for name, days in PERIOD_DAYS.items():
            since = now - timedelta(days=days)
            row = db.execute(
                select(
                    func.coalesce(func.avg(BehaviorMetrics.time_on_page), 0),
                    func.coalesce(func.max(BehaviorMetrics.time_on_page), 0),
                    func.count(),
                ).where(BehaviorMetrics.created_at >= since)
            ).one()
            periods[name] = {"avg_sec": round(float(row[0]), 1), "max_sec": int(row[1]), "sessions": int(row[2])}

        month_ago = now - timedelta(days=PERIOD_DAYS["month"])
        # Курсор: каждая точка {x, y} в долях 0..1 → ячейка сетки 40×40
        heat_rows = db.execute(
            text(
                """
                SELECT LEAST(FLOOR((p->>'x')::float * :g), :g - 1)::int AS gx,
                       LEAST(FLOOR((p->>'y')::float * :g), :g - 1)::int AS gy,
                       COUNT(*) AS cnt
                FROM behavior_metrics m
                CROSS JOIN LATERAL jsonb_array_elements(
                    CASE WHEN jsonb_typeof(m.cursor_positions) = 'array' THEN m.cursor_positions ELSE '[]'::jsonb END
                ) AS p
                WHERE m.created_at >= :since
                  AND jsonb_typeof(p) = 'object' AND p ? 'x' AND p ? 'y'
                GROUP BY 1, 2
                ORDER BY 3 DESC
                """
            ),
            {"g": HEATMAP_GRID, "since": month_ago},
        ).all()
        heatmap = [
            {"x": round((gx + 0.5) / HEATMAP_GRID, 4), "y": round((gy + 0.5) / HEATMAP_GRID, 4), "count": int(c)}
            for gx, gy, c in heat_rows
        ]

        # Кнопки: buttons_clicked = {"имя": число}; служебный ключ raw (непарсящаяся строка) пропускаем
        btn_rows = db.execute(
            text(
                """
                SELECT b.key AS name, SUM(b.value::int) AS cnt
                FROM behavior_metrics m
                CROSS JOIN LATERAL jsonb_each_text(
                    CASE WHEN jsonb_typeof(m.buttons_clicked) = 'object' THEN m.buttons_clicked ELSE '{}'::jsonb END
                ) AS b
                WHERE m.created_at >= :since AND b.key <> 'raw' AND b.value ~ '^[0-9]{1,9}$'
                GROUP BY b.key
                ORDER BY cnt DESC
                LIMIT 10
                """
            ),
            {"since": month_ago},
        ).all()

        # Пропорция страницы для силуэта — по десктопным визитам (на телефоне вёрстка другая)
        aspect = db.scalar(
            select(func.avg(BehaviorMetrics.doc_h * 1.0 / BehaviorMetrics.doc_w)).where(
                BehaviorMetrics.created_at >= month_ago, BehaviorMetrics.doc_w >= 900, BehaviorMetrics.doc_h > 0
            )
        )
        return {
            "periods": periods,
            "heatmap": heatmap,
            "top_buttons": [{"name": n, "count": int(c)} for n, c in btn_rows],
            "grid": HEATMAP_GRID,
            "page_aspect": round(float(aspect), 3) if aspect else 2.2,
            "total_sessions": BehaviorMetricsCRUD.count(db),
            "generated_at": now,
        }
