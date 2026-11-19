"""Проверка балльной системы на 10 тестовых заявках из sql/test_applications.sql.

Тест читает ТОТ ЖЕ SQL-файл, что выполняется в БД (make test-sql): парсит INSERT-ы,
подставляет бюджеты услуг и прогоняет каждую заявку через score_lead().
Ожидание задания: ровно 4 горячих, 3 тёплых, 3 холодных.

    make pytest
    (внутри: docker compose run --rm --no-deps backend python -m pytest -q tests)
"""
import re

import pytest

from app.services.lead_scoring import (
    DEPT_CORPORATE,
    MAX_BUDGET,
    MAX_COMPANY,
    MAX_DEADLINE,
    MAX_NICHE,
    MAX_ROLE,
    MAX_VOLUME,
    DEPT_VIP,
    HOT_THRESHOLD,
    WARM_THRESHOLD,
    parse_budget,
    score_lead,
)
from tests.conftest import SQL_DIR

# Совпадает с scripts/seed_services.py: название → потолок бюджета, ₽
SERVICE_BUDGET_MAX = {
    "Полировка кузова": 60_000,
    "Химчистка салона": 40_000,
    "Керамическое покрытие": 250_000,
    "Оклейка плёнкой PPF": 600_000,
    "Установка аудиосистемы Bose премиум": 500_000,
}

MAXIMUMS = {"budget": MAX_BUDGET, "deadline": MAX_DEADLINE, "company": MAX_COMPANY,
            "role": MAX_ROLE, "volume": MAX_VOLUME, "niche": MAX_NICHE}

INSERT_RE = re.compile(r"INSERT INTO applications\s*\(([^)]*)\)\s*VALUES\s*\(", re.IGNORECASE)
SERVICE_RE = re.compile(r"services\s*=\s*'([^']*)'")


def _split_values(sql: str, start: int) -> tuple[list[str], int]:
    """Разбить VALUES (...) на значения верхнего уровня: учитываем кавычки и вложенные скобки."""
    values, buf, depth, i, in_str = [], [], 0, start, False
    while i < len(sql):
        ch = sql[i]
        if in_str:
            buf.append(ch)
            if ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":  # экранированная кавычка ''
                    buf.append("'")
                    i += 1
                else:
                    in_str = False
        elif ch == "'":
            in_str = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            if depth == 0:
                values.append("".join(buf).strip())
                return values, i
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            values.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    raise ValueError("незакрытая скобка в VALUES")


def _literal(token: str):
    if token.upper() == "NULL":
        return None
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1].replace("''", "'")
    m = SERVICE_RE.search(token)
    if token.startswith("(") and m:
        return {"service": m.group(1)}
    return token  # выражения вроде now() - interval '1 day' — для оценки не нужны


def load_test_applications() -> list[dict]:
    sql = (SQL_DIR / "test_applications.sql").read_text(encoding="utf-8")
    # Комментарии -- ... до конца строки не мешают: в значениях их нет
    apps = []
    for m in INSERT_RE.finditer(sql):
        cols = [c.strip() for c in m.group(1).split(",")]
        values, _ = _split_values(sql, m.end())
        assert len(cols) == len(values), f"столбцов {len(cols)}, значений {len(values)}"
        row = dict(zip(cols, (_literal(v) for v in values)))
        service = row.pop("service_id")
        row["service_name"] = service["service"] if isinstance(service, dict) else None
        apps.append(row)
    return apps


def _score(row: dict):
    return score_lead(row, service_budget_max=SERVICE_BUDGET_MAX.get(row["service_name"]),
                      service_name=row["service_name"])


@pytest.fixture(scope="module")
def apps() -> list[dict]:
    return load_test_applications()


def test_ten_applications_parsed(apps):
    assert len(apps) == 10
    assert all(a["comment"].startswith("[тест-SQL]") for a in apps)
    assert all(a["service_name"] in SERVICE_BUDGET_MAX for a in apps), "услуга не из каталога seed_services.py"


def test_distribution_4_3_3(apps):
    temps = [_score(a).temperature for a in apps]
    assert temps.count("hot") == 4, temps
    assert temps.count("warm") == 3, temps
    assert temps.count("cold") == 3, temps


def test_order_in_file_matches_blocks(apps):
    """В файле: первые 4 — горячие, следующие 3 — тёплые, последние 3 — холодные."""
    temps = [_score(a).temperature for a in apps]
    assert temps == ["hot"] * 4 + ["warm"] * 3 + ["cold"] * 3, [(a["last_name"], _score(a).score) for a in apps]


def test_hot_leads_have_different_strengths(apps):
    """У горячих разные сильные стороны: наборы критериев, набранных на максимум, попарно различны.

    Воронцов — бюджет; Кравцова — срочность; Шестаков — размер компании; Гусейнов — объём парка.
    """
    hot = [_score(a) for a in apps[:4]]
    maxed = [frozenset(k for k, v in s.breakdown.items() if v == MAXIMUMS[k]) for s in hot]
    assert len(set(maxed)) == 4, maxed
    assert "budget" in maxed[0] and "deadline" in maxed[1] and "company" in maxed[2] and "volume" in maxed[3]


def test_scores_within_bounds_and_reasons(apps):
    for a in apps:
        s = _score(a)
        assert 0 <= s.score <= 100
        assert len(s.reasons) == 6
        assert sum(s.breakdown.values()) == s.score
        if s.score >= HOT_THRESHOLD:
            assert s.temperature == "hot" and s.needs_personal_manager
        elif s.score >= WARM_THRESHOLD:
            assert s.temperature == "warm"
        else:
            assert s.temperature == "cold"


def test_huge_budget_needs_vip_manager(apps):
    s = _score(apps[0])  # Воронцов, Bentley, 600 000 ₽
    assert s.needs_personal_manager
    assert s.department == DEPT_VIP
    assert s.breakdown["budget"] == 30


def test_taxi_fleet_goes_to_corporate(apps):
    s = _score(apps[3])  # таксопарк
    assert s.department == DEPT_CORPORATE


def test_empty_application_is_cold():
    s = score_lead({"role": "сотрудник"})
    assert s.temperature == "cold"
    assert s.urgency == "не указана"


@pytest.mark.parametrize("raw,expected", [("180000", 180000), ("180 000 ₽", 180000), (75000, 75000), ("", None), (None, None)])
def test_parse_budget(raw, expected):
    assert parse_budget(raw) == expected


def test_llm_mock_mode_adds_summary(apps):
    s = score_lead(apps[0], service_budget_max=600_000, service_name="Оклейка плёнкой PPF", mode="llm_mock")
    assert s.engine == "llm_mock" and s.ai_summary
