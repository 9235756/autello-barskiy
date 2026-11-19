#!/usr/bin/env python3
"""Запасной способ создать 5 услуг через API с логином админа.
Основной путь по заданию — вручную в таблице на вкладке «Услуги» в /admin.

    python scripts/seed_services.py          (или make seed)

- Входит как DEMO_ADMIN_USER / DEMO_ADMIN_PASSWORD из .env (POST /api/auth/login → JWT).
  Если админов ещё нет — сначала регистрирует демо-админа.
- Идемпотентно: услуга с уже существующим названием не создаётся повторно;
  если она была выключена (is_active=false) — включается обратно.
"""
from _common import ApiError, admin_token, base_url, print_table, request

# Те же 5 услуг и бюджеты использует backend/tests/test_lead_scoring.py
SERVICES = [
    {"services": "Полировка кузова", "budget_range": "15к–60к", "budget_min": 15000, "budget_max": 60000},
    {"services": "Химчистка салона", "budget_range": "10к–40к", "budget_min": 10000, "budget_max": 40000},
    {"services": "Керамическое покрытие", "budget_range": "50к–250к", "budget_min": 50000, "budget_max": 250000},
    {"services": "Оклейка плёнкой PPF", "budget_range": "150к–600к", "budget_min": 150000, "budget_max": 600000},
    {"services": "Установка аудиосистемы Bose премиум", "budget_range": "80к–500к", "budget_min": 80000, "budget_max": 500000},
]


def main() -> None:
    print(f"API: {base_url()}/api/admin-settings")
    token = admin_token()
    _, existing = request("GET", "/api/admin-settings")
    if not isinstance(existing, list):
        raise SystemExit(f"Ожидался массив услуг, пришло: {existing!r}")
    by_name = {s["services"].strip().lower(): s for s in existing}

    rows = []
    for svc in SERVICES:
        found = by_name.get(svc["services"].lower())
        if found:
            if not found["is_active"]:
                request("PUT", f"/api/admin-settings/{found['id']}", {"is_active": True}, token=token)
                rows.append([found["id"], svc["services"], found["budget_range"], "включена снова"])
            else:
                rows.append([found["id"], svc["services"], found["budget_range"], "уже есть"])
            continue
        try:
            status, created = request("POST", "/api/admin-settings", svc, token=token)
            rows.append([created["id"], created["services"], created["budget_range"], f"создана ({status})"])
        except ApiError as exc:
            if exc.status == 409:  # кто-то успел создать параллельно
                rows.append(["—", svc["services"], svc["budget_range"], "уже есть (409)"])
            else:
                raise

    print_table(["id", "Услуга", "Диапазон", "Результат"], rows)
    _, all_items = request("GET", "/api/admin-settings?only_active=true")
    print(f"\nАктивных услуг в GET /api/admin-settings: {len(all_items)}")


if __name__ == "__main__":
    main()
