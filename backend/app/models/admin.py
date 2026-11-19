"""Администраторы сайта: вход в /admin по логину и паролю, дальше — JWT."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.core.security import hash_password


class Admin(Base):
    """Администратор. Пароль хранится только в виде bcrypt-хеша.

    SQL (тот же текст — в sql/schema_part3.sql):

        CREATE TABLE admins (
            id               SERIAL PRIMARY KEY,
            username         VARCHAR(50)  NOT NULL UNIQUE,
            hashed_password  VARCHAR(100) NOT NULL,   -- $2b$12$... (bcrypt, 60 символов)
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
        );
    """

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Admin id={self.id} {self.username!r}>"


class AdminCRUD:
    """Операции с администраторами. Каждый метод сам делает commit."""

    @staticmethod
    def create(db: Session, username: str, password: str) -> Admin:
        obj = Admin(username=username.strip(), hashed_password=hash_password(password))
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get(db: Session, obj_id: int) -> Admin | None:
        return db.get(Admin, obj_id)

    @staticmethod
    def get_by_username(db: Session, username: str) -> Admin | None:
        return db.scalars(select(Admin).where(Admin.username == username.strip())).first()

    @staticmethod
    def get_all(db: Session) -> list[Admin]:
        return list(db.scalars(select(Admin).order_by(Admin.id)))

    @staticmethod
    def count(db: Session) -> int:
        return db.scalar(select(func.count()).select_from(Admin)) or 0

    @staticmethod
    def update_password(db: Session, obj_id: int, password: str) -> Admin | None:
        obj = db.get(Admin, obj_id)
        if obj is None:
            return None
        obj.hashed_password = hash_password(password)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def delete(db: Session, obj_id: int) -> bool:
        obj = db.get(Admin, obj_id)
        if obj is None:
            return False
        db.delete(obj)
        db.commit()
        return True
