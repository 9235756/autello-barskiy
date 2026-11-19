"""Заявки с сайта: приём пакета «заявка + метрики» и просмотр."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.admin_settings import AdminSettingsCRUD
from app.models.application import ApplicationCRUD
from app.schemas.application import ApplicationCreated, ApplicationOut, ApplicationPacket

router = APIRouter(prefix="/applications", tags=["applications (заявки)"])
log = logging.getLogger("autello.applications")


@router.post(
    "",
    response_model=ApplicationCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Принять заявку и метрики одним пакетом",
)
@router.post("/", response_model=ApplicationCreated, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_application(packet: ApplicationPacket, db: Session = Depends(get_db)):
    service = AdminSettingsCRUD.get(db, packet.application.service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=422, detail="Выбранная услуга не найдена или отключена")

    app_obj = ApplicationCRUD.create(
        db,
        data=packet.application.model_dump(),
        metrics=packet.metrics.model_dump(),
    )
    log.info("Новая заявка #%s: %s, услуга «%s»", app_obj.id, app_obj.last_name, service.services)
    return ApplicationCreated(id=app_obj.id)


@router.get("", response_model=list[ApplicationOut], summary="Последние заявки (с метриками)")
@router.get("/", response_model=list[ApplicationOut], include_in_schema=False)
def list_applications(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return ApplicationCRUD.get_all(db, limit=limit, offset=offset)


@router.get("/{item_id}", response_model=ApplicationOut, summary="Заявка с метриками")
@router.get("/{item_id}/", response_model=ApplicationOut, include_in_schema=False)
def get_application(item_id: int, db: Session = Depends(get_db)):
    obj = ApplicationCRUD.get(db, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Заявка {item_id} не найдена")
    return obj
