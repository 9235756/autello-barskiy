"""Проверка живости: backend отвечает И видит базу данных."""
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db

router = APIRouter(prefix="/health", tags=["health"])
log = logging.getLogger("autello.health")


@router.get("", summary="Состояние backend и БД")
@router.get("/", include_in_schema=False)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — любая ошибка БД = нездоров
        log.error("БД недоступна: %s", exc)
        return JSONResponse(status_code=503, content={"status": "error", "db": "error"})
    return {"status": "ok", "db": "ok"}
