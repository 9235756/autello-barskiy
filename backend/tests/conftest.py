"""Общие настройки pytest: путь к пакету app и к каталогу sql/."""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# В контейнере sql/ примонтирован в /srv/sql; локально — ../sql рядом с backend/
SQL_DIR = Path(os.getenv("SQL_DIR", "/srv/sql"))
if not SQL_DIR.exists():
    SQL_DIR = BACKEND.parent / "sql"
