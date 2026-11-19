#!/usr/bin/env python3
"""Разбор JSON-ответов API для scripts/check.sh (чтобы не писать Python внутри bash-кавычек).

    curl ... | python3 scripts/_check_json.py <запрос>

Печатает одну строку. Первое слово OK/FAIL — для запросов-проверок.
"""
import json
import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def stats(d):
    ok = all(k in d["periods"] for k in ("day", "week", "month")) and len(d["heatmap"]) > 0
    names = {"day": "день", "week": "неделя", "month": "месяц"}
    parts = [f"{names[k]}: ср. {v['avg_sec']} с, макс. {v['max_sec']} с, {v['sessions']} сесс." for k, v in d["periods"].items()]
    return ("OK " if ok else "FAIL ") + "; ".join(parts) + f"; heatmap {len(d['heatmap'])} ячеек; кнопок в топе {len(d['top_buttons'])}"


def dist(d):
    temps = [a["scoring"]["temperature"] for a in d if (a.get("comment") or "").startswith("[тест-SQL]")]
    return f"{temps.count('hot')}/{temps.count('warm')}/{temps.count('cold')}"


def top4(d):
    return ", ".join(f"{a['last_name']} {a['scoring']['score']} {a['scoring']['temperature_label']}" for a in d[:4])


def sorted_ok(d):
    return str(all(d[i]["scoring"]["score"] >= d[i + 1]["scoring"]["score"] for i in range(len(d) - 1)))


def summary(d):
    ok = "by_temperature" in d and d["total"] > 0
    t = d["by_temperature"]
    return ("OK " if ok else "FAIL ") + (
        f"всего {d['total']}: 🔥 {t['hot']} / 🌤 {t['warm']} / ❄️ {t['cold']}, средний бюджет {d['avg_budget']}, "
        f"за 7 дней {d['last_7_days']}, за 30 дней {d['last_30_days']}"
    )


def services(d):
    return f"{len(d)} шт.: " + ", ".join(s["services"] for s in d) if isinstance(d, list) else "не массив"


QUERIES = {
    "stats": stats,
    "dist": dist,
    "top4": top4,
    "sorted": sorted_ok,
    "summary": summary,
    "services": services,
    "count": lambda d: str(len(d)) if isinstance(d, list) else "-1",
    "token": lambda d: d.get("access_token", ""),
    "id": lambda d: str(d.get("id", "")),
    "first_id": lambda d: str(d[0]["id"]) if d else "",
}

if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(QUERIES[sys.argv[1]](data))
    except Exception as exc:  # noqa: BLE001 — check.sh покажет текст как результат проверки
        print(f"FAIL ошибка разбора ({type(exc).__name__}: {exc})"[:200])
