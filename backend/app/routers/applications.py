"""Заявки с сайта: приём (публичный) и просмотр с приоритизацией (только админ).

Порядок роутов важен: /ranked и /summary объявлены ДО /{item_id},
иначе FastAPI попытается разобрать «ranked» как номер заявки и вернёт 422.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_admin
from app.models.admin_settings import AdminSettingsCRUD
from app.models.application import Application, ApplicationCRUD
from app.models.behavior_metrics import BehaviorMetricsCRUD
from app.schemas.application import (
    ApplicationCreated,
    ApplicationDetail,
    ApplicationOut,
    ApplicationPacket,
    ApplicationRanked,
    ApplicationsSummary,
)
from app.services.lead_scoring import parse_budget, score_lead

router = APIRouter(prefix="/applications", tags=["applications (заявки)"])
log = logging.getLogger("autello.applications")


def _scored(app: Application) -> dict:
    service = app.service
    result = score_lead(
        app,
        service_budget_max=service.budget_max if service else None,
        service_name=service.services if service else None,
        mode=settings.lead_scoring_mode,
    )
    data = ApplicationOut.model_validate(app).model_dump()
    data["scoring"] = result.as_dict()
    return data


@router.post(
    "",
    response_model=ApplicationCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Принять заявку (публичный)",
)
@router.post("/", response_model=ApplicationCreated, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_application(packet: ApplicationPacket, db: Session = Depends(get_db)):
    service = AdminSettingsCRUD.get(db, packet.application.service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=422, detail="Выбранная услуга не найдена или отключена")

    legacy = None
    if packet.metrics is not None:
        m = packet.metrics
        legacy = {
            "time_on_page": m.time_on_page_sec,
            "buttons_clicked": dict(Counter(c.el for c in m.clicks)),
            "cursor_positions": [],
            "return_frequency": m.return_count,
            "page": "/",
            "extra": {
                "source": "application_packet",
                "utm": m.utm,
                "referrer": m.referrer,
                "user_agent": m.user_agent,
                "screen": m.screen,
                "language": m.language,
                "scroll_depth": m.scroll_depth,
                "hovers": [h.model_dump() for h in m.hovers],
            },
        }
    app_obj = ApplicationCRUD.create(
        db, data=packet.application.model_dump(), session_id=packet.session_id, metrics=legacy
    )
    log.info("Новая заявка #%s: %s, услуга «%s»", app_obj.id, app_obj.last_name, service.services)
    return ApplicationCreated(id=app_obj.id)


@router.get("", response_model=list[ApplicationOut], summary="Последние заявки (нужен токен)")
@router.get("/", response_model=list[ApplicationOut], include_in_schema=False)
def list_applications(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    return ApplicationCRUD.get_all(db, limit=limit, offset=offset)


@router.get(
    "/ranked",
    response_model=list[ApplicationRanked],
    summary="Заявки по «температуре»: score по убыванию (нужен токен)",
)
@router.get("/ranked/", response_model=list[ApplicationRanked], include_in_schema=False)
def ranked(
    temperature: str | None = Query(None, pattern="^(hot|warm|cold)$"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    items = [_scored(a) for a in ApplicationCRUD.get_every(db)]
    if temperature:
        items = [i for i in items if i["scoring"]["temperature"] == temperature]
    # При равном score выше — более свежая заявка
    items.sort(key=lambda i: (i["scoring"]["score"], i["created_at"]), reverse=True)
    return items[:limit]


@router.get("/summary", response_model=ApplicationsSummary, summary="Общая статистика по заявкам (нужен токен)")
@router.get("/summary/", response_model=ApplicationsSummary, include_in_schema=False)
def summary(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    apps = ApplicationCRUD.get_every(db)
    scored = [_scored(a) for a in apps]
    now = datetime.now(timezone.utc)
    temps = Counter(s["scoring"]["temperature"] for s in scored)
    services = Counter(a.service.services if a.service else "Без услуги" for a in apps)
    budgets = [b for b in (parse_budget(a.budget) for a in apps) if b]
    return ApplicationsSummary(
        total=len(apps),
        by_temperature={k: temps.get(k, 0) for k in ("hot", "warm", "cold")},
        by_service=[{"service": name, "count": n} for name, n in services.most_common()],
        avg_budget=round(sum(budgets) / len(budgets)) if budgets else None,
        last_7_days=sum(1 for a in apps if a.created_at >= now - timedelta(days=7)),
        last_30_days=sum(1 for a in apps if a.created_at >= now - timedelta(days=30)),
        needs_personal_manager=sum(1 for s in scored if s["scoring"]["needs_personal_manager"]),
        avg_score=round(sum(s["scoring"]["score"] for s in scored) / len(scored), 1) if scored else 0.0,
    )


@router.get("/{item_id}", response_model=ApplicationDetail, summary="Заявка + оценка + метрики визита (нужен токен)")
@router.get("/{item_id}/", response_model=ApplicationDetail, include_in_schema=False)
def get_application(item_id: int, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    obj = ApplicationCRUD.get(db, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Заявка {item_id} не найдена")
    data = _scored(obj)
    data["metrics"] = BehaviorMetricsCRUD.get_by_application(db, item_id)
    return data
