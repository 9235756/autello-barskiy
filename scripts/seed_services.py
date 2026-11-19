#!/usr/bin/env python3
"""Запасной способ создать 3 услуги через API (основной по заданию — вручную в Swagger /docs).

    python scripts/seed_services.py          (или make seed)

Идемпотентно: услуги с уже существующим названием не создаются повторно.
Запросы идут через nginx: POST http://localhost/api/admin-settings
"""
from _common import ApiError, base_url, print_table, request

SERVICES = [
    {"services": "Полировка кузова", "budget_range": "15к–60к", "budget_min": 15000, "budget_max": 60000},
    {"services": "Химчистка салона", "budget_range": "10к–40к", "budget_min": 10000, "budget_max": 40000},
    {"services": "Керамическое покрытие", "budget_range": "50к–250к", "budget_min": 50000, "budget_max": 250000},
]


def main() -> None:
    print(f"API: {base_url()}/api/admin-settings")
    _, existing = request("GET", "/api/admin-settings")
    by_name = {s["services"].strip().lower(): s for s in existing}

    rows = []
    for svc in SERVICES:
        found = by_name.get(svc["services"].lower())
        if found:
            rows.append([found["id"], svc["services"], found["budget_range"], "уже есть"])
            continue
        try:
            status, created = request("POST", "/api/admin-settings", svc)
            rows.append([created["id"], created["services"], created["budget_range"], f"создана ({status})"])
        except ApiError as exc:
            if exc.status == 409:  # кто-то успел создать параллельно
                rows.append(["—", svc["services"], svc["budget_range"], "уже есть (409)"])
            else:
                raise

    print_table(["id", "Услуга", "Диапазон", "Результат"], rows)
    _, all_items = request("GET", "/api/admin-settings")
    print(f"\nВсего услуг в GET /api/admin-settings: {len(all_items)}")


if __name__ == "__main__":
    main()
