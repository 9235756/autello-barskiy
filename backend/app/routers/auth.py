"""Авторизация админки: первая регистрация, вход (OAuth2 password → JWT), «кто я».

Swagger UI: кнопка Authorize → username/password → Swagger сам вызывает POST /api/auth/login
и дальше подставляет заголовок Authorization: Bearer <token> во все защищённые запросы.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_admin
from app.core.security import create_access_token, verify_password
from app.models.admin import Admin, AdminCRUD
from app.schemas.auth import AdminOut, AdminRegister, AuthCheck, Token

router = APIRouter(prefix="/auth", tags=["auth (вход в админку)"])
log = logging.getLogger("autello.auth")


@router.get("/check", response_model=AuthCheck, summary="Есть ли хотя бы один админ (публичный)")
@router.get("/check/", response_model=AuthCheck, include_in_schema=False)
def check(db: Session = Depends(get_db)):
    # По этому флагу страница входа решает, показывать ли кнопку «Зарегистрироваться»
    return AuthCheck(has_admins=AdminCRUD.count(db) > 0)


@router.post(
    "/register",
    response_model=AdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация ПЕРВОГО админа (если админ уже есть — 403)",
)
@router.post("/register/", response_model=AdminOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def register(payload: AdminRegister, db: Session = Depends(get_db)):
    if AdminCRUD.count(db) > 0:
        raise HTTPException(status_code=403, detail="Администратор уже зарегистрирован. Регистрация закрыта.")
    admin = AdminCRUD.create(db, payload.username, payload.password)
    log.info("Зарегистрирован первый админ: %s", admin.username)
    return admin


@router.post("/login", response_model=Token, summary="Вход: username + password (form-data) → JWT")
@router.post("/login/", response_model=Token, include_in_schema=False)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = AdminCRUD.get_by_username(db, form.username)
    if admin is None or not verify_password(form.password, admin.hashed_password):
        log.warning("Неудачный вход: %s", form.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(admin.username)
    log.info("Вход: %s", admin.username)
    return Token(access_token=token, expires_in=settings.access_token_expire_minutes * 60)


@router.get("/me", response_model=AdminOut, summary="Текущий админ (нужен токен)")
@router.get("/me/", response_model=AdminOut, include_in_schema=False)
def me(admin: Admin = Depends(get_current_admin)):
    return admin
