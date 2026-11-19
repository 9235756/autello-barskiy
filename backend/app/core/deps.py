"""Зависимости FastAPI: текущий админ по Bearer-токену."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.admin import Admin, AdminCRUD

# tokenUrl — путь формы логина. Swagger UI (кнопка Authorize) отправляет туда username/password.
# Путь абсолютный (/api/...), поэтому Authorize работает и на :8000/docs, и через nginx /docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Требуется вход: токен отсутствует, неверен или истёк",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Admin:
    username = decode_access_token(token)
    if username is None:
        raise _UNAUTHORIZED
    admin = AdminCRUD.get_by_username(db, username)
    if admin is None:
        # Токен подписан нашим ключом, но админа уже нет (например, БД пересоздали)
        raise _UNAUTHORIZED
    return admin
