#!/usr/bin/env python3
"""Заглушка «GPT-анализа лида» для следующей части курса. В API пока НЕ подключена.

    python scripts/mock_gpt.py --id 5        # проанализировать заявку №5 (берётся из GET /api/applications/5)
    python scripts/mock_gpt.py --last 3      # три последние заявки
    python scripts/mock_gpt.py --demo        # без API: на встроенном примере

При MOCK_MODE=true ответ генерируется локально и детерминированно (одна и та же заявка →
один и тот же результат), ключ OPENAI_API_KEY не нужен. Формат ответа совпадает с тем,
что будем просить у модели: {"lead_score": 0–100, "segment": "...", "summary": "..."}.
"""
import argparse
import hashlib
import json
import random

from _common import load_env, request

DEMO = {
    "id": 0, "last_name": "Барский", "first_name": "Андрей", "business_niche": "Автосалон", "role": "руководитель",
    "service_name": "Керамическое покрытие", "budget": "180000", "deadline": "В течение недели",
    "need_volume": "6–20 автомобилей", "product_interest": "Корпоративный договор", "contact_method": "telegram",
    "metrics": {"time_on_page_sec": 312, "clicks": [{}] * 14, "return_count": 2, "scroll_depth": 100,
                "utm": {"utm_source": "yandex", "utm_medium": "cpc"}},
}


def score_lead(app: dict) -> dict:
    """Эвристика вместо модели: те же сигналы, которые позже уйдут в промт GPT."""
    m = app.get("metrics") or {}
    score = 30
    score += 15 if app.get("role") == "руководитель" else 0
    score += {"Как можно скорее": 15, "В течение недели": 10, "В течение месяца": 5}.get(app.get("deadline") or "", 0)
    score += {"Корпоративный договор": 12, "Абонемент на уход": 8, "Комплекс услуг": 6}.get(app.get("product_interest") or "", 0)
    score += 10 if (app.get("need_volume") or "").startswith(("6", "Более")) else 0
    score += min(10, (m.get("time_on_page_sec") or 0) // 60)
    score += min(5, len(m.get("clicks") or []) // 4)
    score += 3 * min(2, m.get("return_count") or 0)
    # Небольшой детерминированный «шум», как у живой модели
    seed = int(hashlib.sha256(json.dumps(app, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(), 16)
    score += random.Random(seed).randint(-4, 4)
    score = max(0, min(100, score))

    niche = app.get("business_niche") or "клиент"
    if score >= 75:
        segment = "горячий"
    elif score >= 50:
        segment = "тёплый"
    else:
        segment = "холодный"
    fleet = "автопарк" if niche in ("Такси-парк", "Автосалон") else "частный автомобиль"
    budget = f'{int(app["budget"]):,}'.replace(",", " ") + " ₽" if (app.get("budget") or "").isdigit() else "не указан"
    summary = (
        f"{niche}, {app.get('role') or 'роль не указана'}; интерес — «{app.get('service_name') or 'услуга'}», "
        f"бюджет {budget}, {fleet}. Срок: {(app.get('deadline') or 'не указан').lower()}. "
        f"Провёл на сайте {m.get('time_on_page_sec', 0)} с, возвращался {m.get('return_count', 0)} раз. "
        + ("Рекомендуем связаться в течение часа." if segment == "горячий" else
           "Отправить персональное предложение." if segment == "тёплый" else "Добавить в прогревающую рассылку.")
    )
    return {"application_id": app.get("id"), "lead_score": score, "segment": segment, "summary": summary, "model": "mock-gpt"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--id", type=int, help="номер заявки")
    g.add_argument("--last", type=int, help="N последних заявок")
    g.add_argument("--demo", action="store_true", help="встроенный пример без обращения к API")
    args = ap.parse_args()

    env = load_env()
    if env.get("MOCK_MODE", "true").lower() != "true":
        raise SystemExit(
            "MOCK_MODE=false: реальный вызов OpenAI появится в следующей части курса "
            f"(модель {env.get('OPENAI_MODEL', 'gpt-4o-mini')}). Пока запускайте с MOCK_MODE=true."
        )

    if args.demo or (args.id is None and args.last is None):
        apps = [DEMO]
    elif args.id is not None:
        apps = [request("GET", f"/api/applications/{args.id}")[1]]
    else:
        apps = request("GET", f"/api/applications?limit={args.last}")[1]

    for app in apps:
        print(json.dumps(score_lead(app), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
