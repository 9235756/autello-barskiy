"""Поведенческие метрики посетителя — одна строка на одну заявку (связь 1:1)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.db import Base


class BehaviorMetrics(Base):
    """Как человек вёл себя на странице, пока заполнял заявку.

    application_id — одновременно PRIMARY KEY и FOREIGN KEY: у заявки не может быть
    двух строк метрик, а метрики без заявки не существуют (связь строго 1:1).

    SQL, который создаёт SQLAlchemy (create_all):

        CREATE TABLE behavior_metrics (
            application_id   INTEGER PRIMARY KEY
                             REFERENCES applications (id) ON DELETE CASCADE,
            time_on_page_sec INTEGER NOT NULL DEFAULT 0,
            clicks           JSONB   NOT NULL DEFAULT '[]',  -- [{"el": "submit", "t": 41.2}, ...]
            hovers           JSONB   NOT NULL DEFAULT '[]',  -- [{"el": "service", "ms": 1830}, ...]
            return_count     INTEGER NOT NULL DEFAULT 0,     -- сколько раз возвращался на вкладку
            scroll_depth     INTEGER NOT NULL DEFAULT 0,     -- максимальная глубина прокрутки, %
            utm              JSONB   NOT NULL DEFAULT '{}',  -- {"utm_source": "yandex", ...}
            referrer         TEXT,
            user_agent       TEXT,
            screen           VARCHAR(30),                    -- "1920x1080"
            language         VARCHAR(20),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """

    __tablename__ = "behavior_metrics"

    application_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True
    )
    time_on_page_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    clicks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    hovers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    return_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    scroll_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    utm: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    referrer: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    screen: Mapped[str | None] = mapped_column(String(30))
    language: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped["Application"] = relationship(back_populates="metrics")  # noqa: F821


class BehaviorMetricsCRUD:
    """Операции с метриками. commit=False — когда метрики пишутся в общей транзакции с заявкой."""

    @staticmethod
    def create(db: Session, application_id: int, data: dict, commit: bool = True) -> BehaviorMetrics:
        obj = BehaviorMetrics(application_id=application_id, **data)
        db.add(obj)
        if commit:
            db.commit()
            db.refresh(obj)
        return obj

    @staticmethod
    def get(db: Session, application_id: int) -> BehaviorMetrics | None:
        return db.get(BehaviorMetrics, application_id)

    @staticmethod
    def get_all(db: Session, limit: int = 100, offset: int = 0) -> list[BehaviorMetrics]:
        stmt = (
            select(BehaviorMetrics)
            .order_by(BehaviorMetrics.application_id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(db.scalars(stmt))

    @staticmethod
    def update(db: Session, application_id: int, data: dict) -> BehaviorMetrics | None:
        obj = db.get(BehaviorMetrics, application_id)
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def delete(db: Session, application_id: int) -> bool:
        obj = db.get(BehaviorMetrics, application_id)
        if obj is None:
            return False
        db.delete(obj)
        db.commit()
        return True
