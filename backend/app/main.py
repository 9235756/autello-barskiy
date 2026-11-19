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
from app.core.migrations import apply_sql_file
from app.routers import admin_settings, applications, auth, behavior_metrics, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autello")


def _create_tables(attempts: int = 15, delay: float = 2.0) -> None:
    """Миграция части 3 → create_all → schema_part3.sql, с повторами: postgres может подняться не сразу."""
    for i in range(1, attempts + 1):
        try:
            # 1) behavior_metrics части 2 (1:1 с заявкой) → анонимный формат части 3
            apply_sql_file("migrate_metrics_part3.sql")
            # 2) недостающие таблицы по моделям (на чистой БД — все)
            Base.metadata.create_all(bind=engine)
            # 3) идемпотентные CREATE/ALTER части 3 (роль «собственник» и т.п.)
            apply_sql_file("schema_part3.sql")
            log.info("Таблицы готовы: %s", ", ".join(sorted(Base.metadata.tables)))
            return
        except OperationalError as exc:
            log.warning("БД недоступна (попытка %s/%s): %s", i, attempts, exc.orig)
            time.sleep(delay)
    raise RuntimeError("Не удалось подключиться к PostgreSQL")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _create_tables()
    if settings.secret_key.startswith("replace_with") or len(settings.secret_key) < 32:
        log.warning("SECRET_KEY не задан или слишком короткий — выполните make secret (openssl rand -hex 32)")
    log.info(
        "MOCK_MODE=%s, DOCS_ENABLED=%s, LEAD_SCORING_MODE=%s, CORS=%s",
        settings.mock_mode, settings.docs_enabled, settings.lead_scoring_mode, settings.cors_list,
    )
    yield


app = FastAPI(
    title="Autello Barskiy API",
    version="3.0.0",
    description=(
        "Услуги, заявки, поведенческие метрики и приоритизация лидов. Все пути — под /api/.\n\n"
        "**Авторизация:** кнопка **Authorize** → логин и пароль админа. "
        "Если админа ещё нет — сначала POST /api/auth/register."
    ),
    # DOCS_ENABLED=false (secure-режим) → /docs и /openapi.json не существуют (404)
    docs_url="/docs" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
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


for r in (health.router, auth.router, admin_settings.router, applications.router, behavior_metrics.router):
    app.include_router(r, prefix="/api")
