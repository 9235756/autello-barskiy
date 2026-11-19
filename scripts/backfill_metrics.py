#!/usr/bin/env python3
"""Историческая активность для «Статистики пользователей»: ~300 визитов за последние 30 дней.

    python scripts/backfill_metrics.py            (или make backfill)
    python scripts/backfill_metrics.py -n 500     # больше визитов
    python scripts/backfill_metrics.py --dry-run  # только напечатать SQL

Зачем: живые визиты (Playwright или вы сами) дают данные только «за сегодня», а средние
за неделю и месяц без истории пустые. Скрипт вставляет визиты напрямую в behavior_metrics
через psql в контейнере postgres (backend не нужен, порт БД наружу не открываем).

Распределения:
- время на странице 20–400 с (логнормальное, чаще 60–150 с);
- курсор кластеризуется вокруг поля услуги, ползунка бюджета и кнопки «Отправить»
  (координаты элементов в долях документа замерены Playwright на 1366×900);
- ~10 визитов за последние сутки, ~25% — за последнюю неделю.

Повторный запуск безопасен: прежние строки с session_id «backfill-…» сначала удаляются.
"""
import argparse
import json
import random
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

from _common import ROOT, load_env

# Центры элементов главной в долях ширины/высоты документа — замер Playwright на 1366×900
# (make e2e пишет reports/page_geometry.json; при изменении вёрстки обновите значения).
DOC_W, DOC_H = 1366, 2671
HOTSPOTS = {
    # имя: (x, y, вес, σx, σy) — σ в долях: 0.05 ширины ≈ 68 px, 0.01 высоты ≈ 27 px
    "service": (0.405, 0.317, 0.30, 0.09, 0.008),
    "budget": (0.405, 0.368, 0.24, 0.12, 0.007),
    "submit": (0.196, 0.916, 0.14, 0.035, 0.007),
    "contacts": (0.40, 0.48, 0.12, 0.13, 0.03),
    "task": (0.40, 0.64, 0.10, 0.13, 0.04),
    "hero": (0.42, 0.07, 0.10, 0.18, 0.025),
}
BUTTONS = ["service", "budget", "role_head", "role_staff", "cm_phone", "cm_telegram", "cm_whatsapp",
           "cm_email", "last_name", "first_name", "phone", "email", "business_niche", "deadline", "submit"]
VIEWPORTS = [(1366, 900), (1920, 1080), (1536, 864), (1440, 900), (390, 844), (412, 915)]


def time_on_page(rng: random.Random) -> int:
    return int(min(400, max(20, rng.lognormvariate(4.6, 0.55))))


def created_at(rng: random.Random, now: datetime, i: int, n: int) -> datetime:
    if i < 10:  # гарантированно есть данные «за день»
        return now - timedelta(minutes=rng.randint(5, 23 * 60))
    if i < n // 4:  # и «за неделю»
        return now - timedelta(hours=rng.uniform(24, 7 * 24))
    return now - timedelta(hours=rng.uniform(7 * 24, 30 * 24 - 1))


def cursor(rng: random.Random, seconds: int) -> list[dict]:
    names = list(HOTSPOTS)
    weights = [HOTSPOTS[k][2] for k in names]
    points = []
    spot = rng.choices(names, weights)[0]
    for _ in range(min(seconds, 150)):  # одна точка в секунду, как у фронта; не больше 150
        if rng.random() < 0.18:  # курсор перешёл к другому элементу
            spot = rng.choices(names, weights)[0]
        x, y, _, sx, sy = HOTSPOTS[spot]
        points.append({"x": round(min(1, max(0, rng.gauss(x, sx))), 4), "y": round(min(1, max(0, rng.gauss(y, sy))), 4)})
    return points


def buttons(rng: random.Random, seconds: int) -> dict:
    clicks = {"service": rng.randint(1, 3)}
    if rng.random() < 0.8:
        clicks["budget"] = rng.randint(1, 5)
    for name in rng.sample(BUTTONS[2:-1], k=rng.randint(0, 6)):
        clicks[name] = rng.randint(1, 2)
    if seconds > 60 and rng.random() < 0.35:
        clicks["submit"] = 1
    return clicks


def q(value) -> str:
    """Литерал SQL: строки и JSON экранируем удвоением кавычек."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(n: int, seed: int | None) -> str:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n):
        sec = time_on_page(rng)
        vw, vh = rng.choice(VIEWPORTS)
        start = created_at(rng, now, i, n)
        extra = {"source": "backfill", "utm": rng.choice([{}, {"utm_source": "yandex"}, {"utm_source": "vk"}, {"utm_source": "telegram"}])}
        rows.append("(" + ", ".join([
            q(f"backfill-{uuid.UUID(int=rng.getrandbits(128))}"),
            "NULL",
            q(sec),
            q(buttons(rng, sec)) + "::jsonb",
            q(cursor(rng, sec)) + "::jsonb",
            q(rng.choices([0, 1, 2, 3], [55, 28, 12, 5])[0]),
            q(vw), q(vh), q(DOC_W if vw > 800 else vw), q(DOC_H if vw > 800 else int(DOC_H * 1.9)),
            q("/"),
            q(extra) + "::jsonb",
            q(start.isoformat()),
            q((start + timedelta(seconds=sec)).isoformat()),
        ]) + ")")
    return (
        "BEGIN;\n"
        "DELETE FROM behavior_metrics WHERE session_id LIKE 'backfill-%';\n"
        "INSERT INTO behavior_metrics (session_id, application_id, time_on_page, buttons_clicked, cursor_positions,"
        " return_frequency, viewport_w, viewport_h, doc_w, doc_h, page, extra, created_at, updated_at) VALUES\n"
        + ",\n".join(rows)
        + ";\nCOMMIT;\n"
        "SELECT count(*) AS backfill_rows, round(avg(time_on_page)) AS avg_sec, max(time_on_page) AS max_sec"
        " FROM behavior_metrics WHERE session_id LIKE 'backfill-%';\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=300, help="сколько визитов (по умолчанию 300)")
    ap.add_argument("--seed", type=int, default=None, help="зерно генератора для воспроизводимости")
    ap.add_argument("--dry-run", action="store_true", help="только напечатать SQL")
    args = ap.parse_args()

    sql = build_sql(args.n, args.seed)
    if args.dry_run:
        print(sql)
        return
    env = load_env()
    cmd = ["docker", "compose", "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-q",
           "-U", env.get("POSTGRES_USER", "autello"), "-d", env.get("POSTGRES_DB", "autello")]
    res = subprocess.run(cmd, input=sql, text=True, capture_output=True, cwd=ROOT)
    if res.returncode != 0:
        sys.exit(f"psql завершился с ошибкой:\n{res.stderr}")
    print(res.stdout.strip())
    print(f"Готово: {args.n} исторических визитов за 30 дней в behavior_metrics")


if __name__ == "__main__":
    main()
