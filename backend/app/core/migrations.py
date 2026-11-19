"""Применение SQL-файлов из каталога sql/ при старте backend.

Порядок (см. main.py):
  1. sql/migrate_metrics_part3.sql — переводит behavior_metrics части 2 (1:1 с заявкой)
     в анонимный формат части 3. Идемпотентна: повторный запуск ничего не меняет.
  2. Base.metadata.create_all — создаёт недостающие таблицы (на чистой БД — все).
  3. sql/schema_part3.sql — CREATE ... IF NOT EXISTS и правка CHECK по роли. Тоже идемпотентна.

Файлы выполняются «сырым» соединением psycopg без параметров, поэтому внутри
можно писать DO $$ ... $$ и несколько команд подряд.
"""
import logging
from pathlib import Path

from app.core.config import settings
from app.core.db import engine

log = logging.getLogger("autello.migrations")


def apply_sql_file(name: str) -> bool:
    path = Path(settings.sql_dir) / name
    if not path.exists():
        log.warning("SQL-файл %s не найден (каталог sql/ не примонтирован?) — пропускаю", path)
        return False
    sql = path.read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    log.info("Применён %s", path.name)
    return True
