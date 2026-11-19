"""Подключение к PostgreSQL: engine, фабрика сессий, базовый класс моделей, зависимость get_db."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# pool_pre_ping — перед выдачей соединения из пула проверяем, что оно живо
# (после рестарта postgres не получим «server closed the connection»)
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)

# expire_on_commit=False — после commit объект остаётся заполненным,
# его можно сразу отдать в ответ без повторного SELECT
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс всех моделей SQLAlchemy."""


def get_db() -> Iterator[Session]:
    """Зависимость FastAPI: одна сессия на запрос, закрывается в любом случае."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
