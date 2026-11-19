"""Услуги, которые администратор показывает в выпадающем списке на сайте."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base


class AdminSettings(Base):
    """Услуга автобизнеса и её ценовой диапазон.

    SQL, который создаёт SQLAlchemy (create_all):

        CREATE TABLE admin_settings (
            id            SERIAL PRIMARY KEY,
            services      VARCHAR(200) NOT NULL UNIQUE,  -- название услуги
            budget_range  VARCHAR(50)  NOT NULL,         -- для людей: "50к–250к"
            budget_min    INTEGER      NOT NULL,         -- границы ползунка бюджета, ₽
            budget_max    INTEGER      NOT NULL,
            is_active     BOOLEAN      NOT NULL DEFAULT true,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT ck_admin_settings_budget CHECK (budget_min >= 0 AND budget_min <= budget_max)
        );
    """

    __tablename__ = "admin_settings"
    __table_args__ = (
        CheckConstraint("budget_min >= 0 AND budget_min <= budget_max", name="ck_admin_settings_budget"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    services: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    budget_range: Mapped[str] = mapped_column(String(50), nullable=False)
    budget_min: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_max: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AdminSettings id={self.id} {self.services!r} {self.budget_range}>"


class AdminSettingsCRUD:
    """Операции с услугами. Каждый метод сам делает commit."""

    @staticmethod
    def create(db: Session, data: dict) -> AdminSettings:
        obj = AdminSettings(**data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get(db: Session, obj_id: int) -> AdminSettings | None:
        return db.get(AdminSettings, obj_id)

    @staticmethod
    def get_all(db: Session, only_active: bool = False) -> list[AdminSettings]:
        """ВЕСЬ список услуг (а не «последняя запись») — именно его ждёт выпадающий список."""
        stmt = select(AdminSettings).order_by(AdminSettings.id)
        if only_active:
            stmt = stmt.where(AdminSettings.is_active.is_(True))
        return list(db.scalars(stmt))

    @staticmethod
    def update(db: Session, obj_id: int, data: dict) -> AdminSettings | None:
        obj = db.get(AdminSettings, obj_id)
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def delete(db: Session, obj_id: int) -> bool:
        obj = db.get(AdminSettings, obj_id)
        if obj is None:
            return False
        db.delete(obj)
        db.commit()
        return True
