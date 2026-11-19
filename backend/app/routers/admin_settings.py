"""CRUD услуг: их видит выпадающий список на сайте и таблица в /admin.

Часть 3: GET — публичный (главной нужен список услуг), POST/PUT/DELETE — только с JWT.

Каждый роут зарегистрирован дважды — с путём "" и "/" (дубль скрыт из Swagger).
Вместе с redirect_slashes=False это убирает 307 Redirect: и /api/admin-settings,
и /api/admin-settings/ отвечают сразу, без перенаправления (а после 307 браузер
часто теряет тело POST или уходит на http://backend:8000, которого снаружи нет).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_admin
from app.models.admin_settings import AdminSettingsCRUD
from app.schemas.admin_settings import AdminSettingsCreate, AdminSettingsOut, AdminSettingsUpdate

router = APIRouter(prefix="/admin-settings", tags=["admin-settings (услуги)"])


def _get_or_404(db: Session, item_id: int):
    obj = AdminSettingsCRUD.get(db, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Услуга {item_id} не найдена")
    return obj


@router.get("", response_model=list[AdminSettingsOut], summary="Весь список услуг")
@router.get("/", response_model=list[AdminSettingsOut], include_in_schema=False)
def list_services(
    only_active: bool = Query(False, description="true — только активные (для сайта)"),
    db: Session = Depends(get_db),
):
    return AdminSettingsCRUD.get_all(db, only_active=only_active)


@router.post("", response_model=AdminSettingsOut, status_code=status.HTTP_201_CREATED, summary="Создать услугу (нужен токен)")
@router.post("/", response_model=AdminSettingsOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_service(
    payload: AdminSettingsCreate, db: Session = Depends(get_db), _admin=Depends(get_current_admin)
):
    return AdminSettingsCRUD.create(db, payload.model_dump())


@router.get("/{item_id}", response_model=AdminSettingsOut, summary="Одна услуга")
@router.get("/{item_id}/", response_model=AdminSettingsOut, include_in_schema=False)
def get_service(item_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, item_id)


@router.put("/{item_id}", response_model=AdminSettingsOut, summary="Изменить услугу (нужен токен)")
@router.put("/{item_id}/", response_model=AdminSettingsOut, include_in_schema=False)
def update_service(
    item_id: int, payload: AdminSettingsUpdate, db: Session = Depends(get_db), _admin=Depends(get_current_admin)
):
    current = _get_or_404(db, item_id)
    data = payload.model_dump(exclude_unset=True)
    new_min = data.get("budget_min", current.budget_min)
    new_max = data.get("budget_max", current.budget_max)
    if new_min > new_max:
        raise HTTPException(status_code=422, detail="budget_min не может быть больше budget_max")
    return AdminSettingsCRUD.update(db, item_id, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить услугу (нужен токен)")
@router.delete("/{item_id}/", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def delete_service(item_id: int, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    if not AdminSettingsCRUD.delete(db, item_id):
        raise HTTPException(status_code=404, detail=f"Услуга {item_id} не найдена")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
