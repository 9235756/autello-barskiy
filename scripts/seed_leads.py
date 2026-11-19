#!/usr/bin/env python3
"""Генерирует правдоподобные заявки автобизнеса и вставляет их в таблицу leads.

Вставка идёт через `docker compose exec -T postgres psql` — порт БД наружу
не открыт, поэтому ходим внутрь контейнера. Только стандартная библиотека.

    python3 scripts/seed_leads.py            # 25 заявок
    python3 scripts/seed_leads.py -n 100
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MALE = ["Алексей", "Дмитрий", "Сергей", "Андрей", "Михаил", "Игорь", "Владимир", "Роман", "Олег", "Артём", "Николай", "Павел"]
FEMALE = ["Елена", "Ольга", "Наталья", "Анна", "Марина", "Татьяна", "Ирина", "Светлана", "Юлия", "Екатерина"]
SURNAMES = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Волков", "Соколов", "Лебедев", "Козлов", "Новиков", "Морозов", "Петров", "Фёдоров", "Михайлов", "Орлов"]
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})
BUSINESSES = {
    "Автосервис / СТО": ["Автосервис «Мотор»", "СТО «Гараж 24»", "Техцентр «Пит-Стоп»", "Автосервис «Ключ»"],
    "Магазин автозапчастей": ["Запчасти «Деталь»", "Автомагазин «Шестерёнка»", "«Авто-Склад»"],
    "Дилерский центр": ["ДЦ «Север-Авто»", "Автосалон «Магистраль»"],
    "Шиномонтаж": ["Шиномонтаж «Колесо»", "«Шина-Сервис»"],
    "Детейлинг / автомойка": ["Детейлинг «Блеск»", "Автомойка «Пена»"],
}
BUDGETS = ["до 30 000 ₽", "30 000 – 100 000 ₽", "100 000 – 300 000 ₽", "от 300 000 ₽", None]
METHODS = ["phone", "telegram", "whatsapp", "email"]
COMMENTS = [
    "Две точки, заявки сейчас в тетради и в WhatsApp — теряем клиентов.",
    "Нужна онлайн-запись и напоминания клиентам о ТО.",
    "Интересует учёт запчастей и заказ у поставщиков.",
    "Удобно созвониться после 18:00.",
    "Хотим посмотреть демо, сравниваем с другими CRM.",
    "Сеть из трёх сервисов, нужен единый кабинет.",
    None, None,
]
UTM = [
    {"utm_source": "yandex", "utm_medium": "cpc", "utm_campaign": "sto_moscow"},
    {"utm_source": "vk", "utm_medium": "social", "utm_campaign": "autobiz_target"},
    {"utm_source": "telegram", "utm_medium": "post", "utm_campaign": "channel_autoparts"},
    {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "crm_autoservice"},
    {},
]
REFERRERS = ["https://yandex.ru/", "https://vk.com/", "https://t.me/", "https://www.google.com/", None]
DEVICES = [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1", "390x844", True),
    ("Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36", "412x915", True),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 YaBrowser/24.12", "1920x1080", False),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15", "1512x982", False),
]


def read_env() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        sys.exit("Нет .env — выполните make init")
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def q(value) -> str:
    """SQL-литерал с экранированием одинарных кавычек."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def make_lead(rnd: random.Random) -> dict:
    if rnd.random() < 0.65:
        first, last = rnd.choice(MALE), rnd.choice(SURNAMES)
    else:
        first, last = rnd.choice(FEMALE), rnd.choice(SURNAMES) + "а"
    business = rnd.choice(list(BUSINESSES))
    method = rnd.choice(METHODS)
    email = f"{first.lower().translate(TRANSLIT)}.{last.lower().translate(TRANSLIT)}{rnd.randint(1, 99)}@{rnd.choice(['mail.ru', 'yandex.ru', 'gmail.com'])}"
    ua, screen, touch = rnd.choice(DEVICES)
    created = datetime.now(timezone.utc) - timedelta(minutes=rnd.randint(5, 60 * 24 * 14))
    utm = dict(rnd.choice(UTM))
    fill = rnd.randint(25, 240)
    return {
        "created_at": created.isoformat(timespec="seconds"),
        "name": f"{first} {last}",
        "phone": f"+7 9{rnd.randint(0, 99):02d} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
        "email": email if (method == "email" or rnd.random() < 0.5) else None,
        "company": rnd.choice(BUSINESSES[business]),
        "business_info": business,
        "budget": rnd.choice(BUDGETS),
        "contact_method": method,
        "comment": rnd.choice(COMMENTS),
        "metrics": {
            **utm,
            "referrer": rnd.choice(REFERRERS) if utm else None,
            "landing": "/" + ("?" + "&".join(f"{k}={v}" for k, v in utm.items()) if utm else ""),
            "fill_time_sec": fill,
            "time_on_page_sec": fill + rnd.randint(5, 180),
        },
        "tech_info": {
            "user_agent": ua,
            "language": "ru-RU",
            "screen": screen,
            "touch": touch,
            "timezone": rnd.choice(["Europe/Moscow", "Asia/Yekaterinburg", "Europe/Samara"]),
        },
    }


def build_sql(leads: list[dict]) -> str:
    cols = ["created_at", "name", "phone", "email", "company", "business_info", "budget", "contact_method", "comment", "metrics", "tech_info"]
    rows = []
    for ld in leads:
        vals = [q(ld[c]) for c in cols[:-2]]
        vals += [q(json.dumps(ld["metrics"], ensure_ascii=False)) + "::jsonb", q(json.dumps(ld["tech_info"], ensure_ascii=False)) + "::jsonb"]
        rows.append("(" + ", ".join(vals) + ")")
    return (
        "BEGIN;\n"
        f"INSERT INTO leads ({', '.join(cols)}) VALUES\n" + ",\n".join(rows) + ";\n"
        "COMMIT;\n"
        "SELECT count(*) AS total_leads FROM leads;\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=25, help="сколько заявок (по умолчанию 25)")
    ap.add_argument("--seed", type=int, default=None, help="зерно генератора для воспроизводимости")
    ap.add_argument("--dry-run", action="store_true", help="только напечатать SQL")
    args = ap.parse_args()

    env = read_env()
    rnd = random.Random(args.seed)
    sql = build_sql([make_lead(rnd) for _ in range(args.n)])
    if args.dry_run:
        print(sql)
        return 0

    cmd = ["docker", "compose", "exec", "-T", "postgres",
           "psql", "-v", "ON_ERROR_STOP=1", "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"]]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True, cwd=ROOT)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        print("Ошибка вставки. Контейнер postgres запущен? (make up)", file=sys.stderr)
        return proc.returncode
    print(f"Добавлено заявок: {args.n}")
    print(proc.stdout.strip().splitlines()[-2].strip() + " — всего в таблице leads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
