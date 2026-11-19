"""Заявка клиента с формы на главной странице."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.db import Base
from app.models.admin_settings import AdminSettings
from app.models.behavior_metrics import BehaviorMetricsCRUD

ROLES = ("сотрудник", "руководитель", "собственник")
ROLE_CHECK = "role IN ('сотрудник', 'руководитель', 'собственник')"


class Application(Base):
    """Заявка «тёплого» клиента.

    SQL, который создаёт SQLAlchemy (create_all):

        CREATE TABLE applications (
            id               SERIAL PRIMARY KEY,
            last_name        VARCHAR(100) NOT NULL,
            first_name       VARCHAR(100) NOT NULL,
            middle_name      VARCHAR(100),
            phone            VARCHAR(30)  NOT NULL,
            email            VARCHAR(200),
            service_id       INTEGER REFERENCES admin_settings (id) ON DELETE SET NULL,
            business_niche   VARCHAR(100),   -- автосалон / детейлинг / такси-парк / частник
            company_size     VARCHAR(50),
            task_volume      VARCHAR(100),
            role             VARCHAR(20)  NOT NULL,  -- сотрудник / руководитель / собственник
            need_volume      VARCHAR(100),
            deadline         VARCHAR(100),
            task_type        VARCHAR(100),
            product_interest VARCHAR(100),
            budget           VARCHAR(50),    -- строка; на сайте задаётся ползунком
            contact_method   VARCHAR(30),
            contact_time     VARCHAR(50),
            comment          TEXT,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT ck_applications_role CHECK (role IN ('сотрудник', 'руководитель', 'собственник'))
        );
        CREATE INDEX ix_applications_created_at ON applications (created_at);

    Часть 3: в CHECK добавлена роль «собственник» (ALTER — в sql/schema_part3.sql).
    Связи с behavior_metrics больше нет: метрики анонимные, номер заявки в них —
    просто число без внешнего ключа.
    """

    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(ROLE_CHECK, name="ck_applications_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    service_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_settings.id", ondelete="SET NULL")
    )
    business_niche: Mapped[str | None] = mapped_column(String(100))
    company_size: Mapped[str | None] = mapped_column(String(50))
    task_volume: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    need_volume: Mapped[str | None] = mapped_column(String(100))
    deadline: Mapped[str | None] = mapped_column(String(100))
    task_type: Mapped[str | None] = mapped_column(String(100))
    product_interest: Mapped[str | None] = mapped_column(String(100))
    budget: Mapped[str | None] = mapped_column(String(50))
    contact_method: Mapped[str | None] = mapped_column(String(30))
    contact_time: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    service: Mapped[AdminSettings | None] = relationship(lazy="joined")

    @property
    def service_name(self) -> str | None:
        return self.service.services if self.service else None


class ApplicationCRUD:
    """Операции с заявками."""

    @staticmethod
    def create(
        db: Session, data: dict, session_id: str | None = None, metrics: dict | None = None
    ) -> Application:
        """Заявка + отметка в метриках — ОДНА транзакция.

        session_id есть → визиту из behavior_metrics проставляется номер заявки.
        Визита нет, но прислали metrics (формат части 2) → пишем их отдельной строкой.
        """
        obj = Application(**data)
        try:
            db.add(obj)
            db.flush()  # получаем obj.id, но ещё не фиксируем транзакцию
            attached = bool(session_id) and BehaviorMetricsCRUD.attach_application(db, session_id, obj.id)
            if not attached and metrics:
                BehaviorMetricsCRUD.create(db, {**metrics, "application_id": obj.id}, commit=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(obj)
        return obj

    @staticmethod
    def get(db: Session, obj_id: int) -> Application | None:
        return db.get(Application, obj_id)

    @staticmethod
    def get_all(db: Session, limit: int = 50, offset: int = 0) -> list[Application]:
        stmt = select(Application).order_by(Application.id.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt).unique())

    @staticmethod
    def get_every(db: Session) -> list[Application]:
        """Все заявки — для ранжирования и сводки (их сотни, не миллионы)."""
        return list(db.scalars(select(Application).order_by(Application.id)).unique())

    @staticmethod
    def update(db: Session, obj_id: int, data: dict) -> Application | None:
        obj = db.get(Application, obj_id)
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def delete(db: Session, obj_id: int) -> bool:
        obj = db.get(Application, obj_id)
        if obj is None:
            return False
        db.delete(obj)  # метрики анонимные и остаются: связи нет
        db.commit()
        return True
