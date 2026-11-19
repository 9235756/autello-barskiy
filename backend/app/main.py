"""Точка входа FastAPI-приложения Autello Barskiy."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from app import models  # noqa: F401 — регистрирует все таблицы в Base.metadata
from app.core.config import settings
from app.core.db import Base, engine
from app.routers import admin_settings, applications, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autello")


def _create_tables(attempts: int = 15, delay: float = 2.0) -> None:
    """create_all с повторами: postgres может ещё принимать соединения не сразу."""
    for i in range(1, attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            log.info("Таблицы готовы: %s", ", ".join(sorted(Base.metadata.tables)))
            return
        except OperationalError as exc:
            log.warning("БД недоступна (попытка %s/%s): %s", i, attempts, exc.orig)
            time.sleep(delay)
    raise RuntimeError("Не удалось подключиться к PostgreSQL")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _create_tables()
    log.info("MOCK_MODE=%s, DOCS_ENABLED=%s, CORS=%s", settings.mock_mode, settings.docs_enabled, settings.cors_list)
    yield


app = FastAPI(
    title="Autello Barskiy API",
    version="2.0.0",
    description="Услуги, заявки и поведенческие метрики. Все пути — под /api/.",
    docs_url="/docs",
    openapi_url="/openapi.json",
    redoc_url=None,
    # Не отвечать 307 на «лишний/недостающий» слэш — дубли путей заведены в роутерах
    redirect_slashes=False,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    # Нарушение UNIQUE/CHECK/FK — это ошибка клиента, а не 500
    log.warning("IntegrityError: %s", exc.orig)
    msg = str(exc.orig).splitlines()[0] if exc.orig else "Нарушение ограничений БД"
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        msg = "Запись с таким названием уже существует"
    return JSONResponse(status_code=409, content={"detail": msg})


for r in (health.router, admin_settings.router, applications.router):
    app.include_router(r, prefix="/api")
