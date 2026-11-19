"""Поведенческие метрики главной страницы.

POST — публичный (его зовёт главная раз в секунду), GET — только для админа.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_admin
from app.models.behavior_metrics import BehaviorMetricsCRUD
from app.schemas.behavior_metrics import BehaviorMetricsIn, BehaviorMetricsOut, BehaviorStats

router = APIRouter(prefix="/behavior-metrics", tags=["behavior-metrics (метрики)"])


@router.post(
    "",
    response_model=BehaviorMetricsOut,
    status_code=status.HTTP_201_CREATED,
    summary="Принять снимок метрик (публичный). С session_id — upsert",
)
@router.post("/", response_model=BehaviorMetricsOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def save_metrics(payload: BehaviorMetricsIn, db: Session = Depends(get_db)):
    return BehaviorMetricsCRUD.upsert(db, payload.model_dump())


@router.get("", response_model=list[BehaviorMetricsOut], summary="Список визитов (нужен токен)")
@router.get("/", response_model=list[BehaviorMetricsOut], include_in_schema=False)
def list_metrics(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    return BehaviorMetricsCRUD.get_all(db, skip=skip, limit=limit)


@router.get(
    "/stats",
    response_model=BehaviorStats,
    summary="Среднее/максимум за день/неделю/месяц, heatmap 40×40, топ кнопок (нужен токен)",
)
@router.get("/stats/", response_model=BehaviorStats, include_in_schema=False)
def stats(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return BehaviorMetricsCRUD.stats(db)
