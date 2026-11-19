"""Приоритизация лидов: прозрачная балльная система 0–100 с объяснением.

Каждый критерий даёт баллы и строку в reasons[] — менеджер видит, ПОЧЕМУ заявка горячая.

    Критерий                                     Максимум
    бюджет относительно budget_max услуги             30
    срок (срочно / неделя / месяц / не спешу)          25
    размер компании                                   15
    роль (собственник/руководитель > сотрудник)        10
    объём задачи (машин, регулярность)                10
    соответствие нише                                 10
                                                     ----
                                                      100

Температура: hot ≥ 70, warm 40–69, cold < 40.

Модуль не зависит от БД и FastAPI: на вход — словарь или объект заявки и бюджет услуги.
Поэтому его легко тестировать (tests/test_lead_scoring.py) и вызывать из любого места.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

# ---------- Пороги и веса (меняйте здесь, а не в коде функций) ----------

HOT_THRESHOLD = 70
WARM_THRESHOLD = 40
# Бюджет, начиная с которого клиенту нужен персональный менеджер, ₽
PERSONAL_MANAGER_BUDGET = 500_000
# Частник с таким бюджетом считается премиальным, даже если марку не назвал, ₽
PREMIUM_PRIVATE_BUDGET = 300_000

MAX_BUDGET, MAX_DEADLINE, MAX_COMPANY, MAX_ROLE, MAX_VOLUME, MAX_NICHE = 30, 25, 15, 10, 10, 10

# (доля от budget_max услуги, баллы) — первая подходящая ступень
BUDGET_STEPS = ((0.9, 30), (0.7, 24), (0.5, 18), (0.3, 10), (0.0, 4))

DEADLINE_POINTS = {
    "как можно скорее": (25, "высокая"),
    "в течение недели": (18, "средняя"),
    "в течение месяца": (10, "низкая"),
    "не срочно": (3, "низкая"),
}
DEADLINE_UNKNOWN = (5, "не указана")

COMPANY_POINTS = {
    "более 200 человек": 15,
    "51–200 человек": 12,
    "11–50 человек": 9,
    "2–10 человек": 5,
    "только я": 2,
}

ROLE_POINTS = {"собственник": 10, "руководитель": 10, "сотрудник": 4}

NEED_VOLUME_POINTS = {
    "более 20 автомобилей": 10,
    "6–20 автомобилей": 8,
    "2–5 автомобилей": 5,
    "1 автомобиль": 2,
}
TASK_VOLUME_POINTS = {
    "регулярное обслуживание автопарка": 8,
    "несколько раз в год": 5,
    "разовая услуга": 2,
}

NICHE_POINTS = {
    "автосалон": 10,
    "такси-парк": 10,
    "детейлинг-центр": 8,
    "каршеринг / прокат": 6,
    "частный владелец": 5,  # премиум-частник получает 10, см. _niche()
    "другое": 2,
}
CORPORATE_NICHES = {"автосалон", "такси-парк", "каршеринг / прокат"}
CORPORATE_SIZES = {"51–200 человек", "более 200 человек"}

PREMIUM_BRANDS = re.compile(
    r"porsche|bentley|rolls|maybach|ferrari|lamborghini|aston|mclaren|maserati|range rover|"
    r"mercedes|bmw|audi|lexus|genesis|g-class|g-klasse|cayenne|panamera",
    re.IGNORECASE,
)

DEPT_CORPORATE = "Корпоративный отдел"
DEPT_VIP = "VIP-менеджер"
DEPT_RETAIL = "Розничные продажи"

TEMPERATURE_LABEL = {"hot": "🔥 горячий", "warm": "🌤 тёплый", "cold": "❄️ холодный"}


@dataclass
class LeadScore:
    score: int
    temperature: str  # hot / warm / cold
    temperature_label: str
    urgency: str  # высокая / средняя / низкая / не указана
    needs_personal_manager: bool
    department: str
    recommended_action: str
    reasons: list[str] = field(default_factory=list)
    breakdown: dict[str, int] = field(default_factory=dict)
    engine: str = "rules"
    ai_summary: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------- Вспомогательные функции ----------

def _get(app: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(app, Mapping):
        return app.get(key)
    return getattr(app, key, None)


def _norm(v: Any) -> str:
    return str(v).strip().lower() if v not in (None, "") else ""


def parse_budget(v: Any) -> int | None:
    """«180000», «180 000 ₽», 180000 → 180000. Пусто или мусор → None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


def _rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


# ---------- Критерии ----------

def _budget(budget: int | None, budget_max: int | None) -> tuple[int, str]:
    if budget is None:
        return 0, "Бюджет не указан: 0 баллов"
    if budget >= PERSONAL_MANAGER_BUDGET:
        return MAX_BUDGET, f"Крупный бюджет {_rub(budget)} (≥ {_rub(PERSONAL_MANAGER_BUDGET)}): +{MAX_BUDGET}"
    if not budget_max:
        return 10, f"Бюджет {_rub(budget)}, потолок услуги неизвестен: +10"
    ratio = budget / budget_max
    for threshold, points in BUDGET_STEPS:
        if ratio >= threshold:
            return points, f"Бюджет {_rub(budget)} — {round(ratio * 100)}% от максимума услуги: +{points}"
    return 0, "Бюджет не оценён"  # недостижимо: последняя ступень 0.0


def _deadline(deadline: Any) -> tuple[int, str, str]:
    points, urgency = DEADLINE_POINTS.get(_norm(deadline), DEADLINE_UNKNOWN)
    label = deadline or "не указан"
    return points, urgency, f"Срок «{label}»: +{points}"


def _company(size: Any) -> tuple[int, str]:
    points = COMPANY_POINTS.get(_norm(size), 0)
    return points, f"Размер компании «{size or 'не указан'}»: +{points}"


def _role(role: Any) -> tuple[int, str]:
    points = ROLE_POINTS.get(_norm(role), 0)
    return points, f"Роль «{role or 'не указана'}»: +{points}"


def _volume(need_volume: Any, task_volume: Any) -> tuple[int, str]:
    a = NEED_VOLUME_POINTS.get(_norm(need_volume), 0)
    b = TASK_VOLUME_POINTS.get(_norm(task_volume), 0)
    points = min(MAX_VOLUME, max(a, b))
    parts = [p for p in (need_volume, task_volume) if p]
    return points, f"Объём задачи «{', '.join(parts) or 'не указан'}»: +{points}"


def _is_premium_private(niche: str, comment: Any, budget: int | None) -> bool:
    if niche != "частный владелец":
        return False
    return bool(PREMIUM_BRANDS.search(str(comment or ""))) or (budget or 0) >= PREMIUM_PRIVATE_BUDGET


def _niche(niche_raw: Any, comment: Any, budget: int | None) -> tuple[int, str]:
    niche = _norm(niche_raw)
    if _is_premium_private(niche, comment, budget):
        return MAX_NICHE, f"Премиум-частник (марка или бюджет): +{MAX_NICHE}"
    points = NICHE_POINTS.get(niche, 0)
    return points, f"Ниша «{niche_raw or 'не указана'}»: +{points}"


def _temperature(score: int) -> str:
    if score >= HOT_THRESHOLD:
        return "hot"
    if score >= WARM_THRESHOLD:
        return "warm"
    return "cold"


def _department(niche: str, size: str, personal_manager: bool) -> str:
    if niche in CORPORATE_NICHES or size in CORPORATE_SIZES:
        return DEPT_CORPORATE
    if personal_manager:
        return DEPT_VIP
    return DEPT_RETAIL


_CONTACT = {"phone": "позвонить", "telegram": "написать в Telegram", "whatsapp": "написать в WhatsApp", "email": "написать на email"}


def _action(temperature: str, contact_method: Any, personal_manager: bool) -> str:
    how = _CONTACT.get(_norm(contact_method), "связаться")
    if temperature == "hot":
        base = f"{how.capitalize()} в течение 15 минут и подготовить персональное КП"
        return base + (", закрепить персонального менеджера" if personal_manager else "")
    if temperature == "warm":
        return f"{how.capitalize()} сегодня, отправить прайс и кейсы, договориться об осмотре"
    return f"{how.capitalize()} в течение недели, добавить в рассылку с акциями"


def _mock_ai_summary(app: Any, result: LeadScore, service_name: str | None) -> str:
    """Эмуляция «ИИ-оценки» (LEAD_SCORING_MODE=llm_mock): текст собирается локально,
    без внешних вызовов. Детерминирован: одна и та же заявка — один и тот же текст."""
    name = " ".join(x for x in (_get(app, "first_name"), _get(app, "last_name")) if x) or "Клиент"
    seed = int(hashlib.sha256(f"{name}{result.score}".encode()).hexdigest()[:6], 16)
    tones = ["Похоже,", "Судя по заявке,", "Вероятно,"]
    mood = {"hot": "готов покупать в ближайшие дни", "warm": "сравнивает предложения", "cold": "пока присматривается"}
    return (
        f"{tones[seed % 3]} {name} {mood[result.temperature]}. "
        f"Интерес: {service_name or 'услуга не выбрана'}. Ключевой фактор: {result.reasons[0].split(':')[0].lower()}."
    )


# ---------- Публичная функция ----------

def score_lead(
    app: Mapping[str, Any] | Any,
    service_budget_max: int | None = None,
    service_name: str | None = None,
    mode: str = "rules",
) -> LeadScore:
    """Оценить заявку. app — словарь или ORM-объект Application."""
    budget = parse_budget(_get(app, "budget"))
    niche = _norm(_get(app, "business_niche"))
    size = _norm(_get(app, "company_size"))

    b_pts, b_reason = _budget(budget, service_budget_max)
    d_pts, urgency, d_reason = _deadline(_get(app, "deadline"))
    c_pts, c_reason = _company(_get(app, "company_size"))
    r_pts, r_reason = _role(_get(app, "role"))
    v_pts, v_reason = _volume(_get(app, "need_volume"), _get(app, "task_volume"))
    n_pts, n_reason = _niche(_get(app, "business_niche"), _get(app, "comment"), budget)

    breakdown = {"budget": b_pts, "deadline": d_pts, "company": c_pts, "role": r_pts, "volume": v_pts, "niche": n_pts}
    score = max(0, min(100, sum(breakdown.values())))
    temperature = _temperature(score)
    personal_manager = temperature == "hot" or (budget or 0) >= PERSONAL_MANAGER_BUDGET

    # Причины — от самой весомой к самой слабой
    reasons = [r for _, r in sorted(
        zip((b_pts, d_pts, c_pts, r_pts, v_pts, n_pts), (b_reason, d_reason, c_reason, r_reason, v_reason, n_reason)),
        key=lambda pr: -pr[0],
    )]
    result = LeadScore(
        score=score,
        temperature=temperature,
        temperature_label=TEMPERATURE_LABEL[temperature],
        urgency=urgency,
        needs_personal_manager=personal_manager,
        department=_department(niche, size, personal_manager),
        recommended_action=_action(temperature, _get(app, "contact_method"), personal_manager),
        reasons=reasons,
        breakdown=breakdown,
        engine="rules",
    )
    if mode == "llm_mock":
        result.engine = "llm_mock"
        result.ai_summary = _mock_ai_summary(app, result, service_name)
    return result
