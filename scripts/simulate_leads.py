#!/usr/bin/env python3
"""Эмуляция клиентов: N заявок с поведенческими метриками → POST /api/applications через nginx.

    python scripts/simulate_leads.py          # 10 заявок (make leads)
    python scripts/simulate_leads.py -n 50    # больше
    python scripts/simulate_leads.py --seed 7 # воспроизводимый набор

Проверяет всю цепочку «клиент → nginx → backend → PostgreSQL» тем же пакетом,
который отправляет форма на сайте: {"application": {...}, "metrics": {...}}.
"""
import argparse
import random

from _common import ApiError, base_url, print_table, request

MALE = [("Иванов", "Алексей", "Сергеевич"), ("Смирнов", "Дмитрий", "Андреевич"), ("Кузнецов", "Михаил", "Олегович"),
        ("Попов", "Игорь", "Викторович"), ("Соколов", "Артём", "Павлович"), ("Лебедев", "Роман", "Игоревич"),
        ("Новиков", "Сергей", "Александрович"), ("Морозов", "Евгений", "Николаевич"), ("Волков", "Константин", "Юрьевич"),
        ("Фёдоров", "Владимир", "Дмитриевич"), ("Орлов", "Никита", "Ильич"), ("Захаров", "Павел", "Евгеньевич")]
FEMALE = [("Петрова", "Анна", "Михайловна"), ("Васильева", "Екатерина", "Сергеевна"), ("Павлова", "Ольга", "Игоревна"),
          ("Семёнова", "Мария", "Алексеевна"), ("Голубева", "Ирина", "Владимировна"), ("Виноградова", "Татьяна", "Андреевна"),
          ("Белова", "Наталья", "Олеговна"), ("Козлова", "Дарья", "Романовна")]

NICHES = ["Автосалон", "Детейлинг-центр", "Такси-парк", "Частный владелец"]
COMPANY_SIZE = {"Частный владелец": ["Только я"], "Детейлинг-центр": ["2–10 человек", "11–50 человек"],
                "Автосалон": ["11–50 человек", "51–200 человек", "Более 200 человек"],
                "Такси-парк": ["11–50 человек", "51–200 человек", "Более 200 человек"]}
NEED_VOLUME = {"Частный владелец": ["1 автомобиль", "2–5 автомобилей"],
               "Детейлинг-центр": ["2–5 автомобилей", "6–20 автомобилей"],
               "Автосалон": ["6–20 автомобилей", "Более 20 автомобилей"],
               "Такси-парк": ["Более 20 автомобилей", "6–20 автомобилей"]}
TASK_VOLUME = ["Разовая услуга", "Несколько раз в год", "Регулярное обслуживание автопарка"]
DEADLINES = ["Как можно скорее", "В течение недели", "В течение месяца", "Не срочно"]
TASK_TYPES = ["Защита нового автомобиля", "Восстановление внешнего вида", "Предпродажная подготовка", "Регулярный уход"]
INTEREST = ["Только выбранная услуга", "Комплекс услуг", "Абонемент на уход", "Корпоративный договор"]
CONTACT = ["phone", "telegram", "whatsapp", "email"]
CONTACT_TIME = [None, "Утро, 9:00–12:00", "День, 12:00–17:00", "Вечер, 17:00–21:00"]
CARS = ["BMW X5", "Mercedes-Benz GLE", "Porsche Cayenne", "Audi Q7", "Lexus LX", "Toyota Camry", "Kia K5",
        "Range Rover Sport", "Genesis G80", "Hyundai Sonata", "Volkswagen Tiguan", "Haval Jolion"]
COMMENTS = ["{car}, кузов в мелких царапинах после мойки.", "{car}, хочу защитить до первой зимы.",
            "Нужен расчёт на {car} и ещё пару машин.", "{car}, после покупки с пробегом — освежить салон.",
            "Готовим {car} к продаже, нужен товарный вид.", None]
UTM = [
    {"utm_source": "yandex", "utm_medium": "cpc", "utm_campaign": "detailing_msk"},
    {"utm_source": "vk", "utm_medium": "social", "utm_campaign": "ceramic_autumn"},
    {"utm_source": "telegram", "utm_medium": "post", "utm_campaign": "channel_autoclub"},
    {"utm_source": "yandex", "utm_medium": "organic"},
    {},
]
REFERRERS = {"yandex": "https://yandex.ru/", "vk": "https://vk.com/", "telegram": "https://t.me/"}
UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
]
SCREENS = {0: "1920x1080", 1: "393x852", 2: "1512x982", 3: "412x915", 4: "2560x1440"}
TRACKED = ["service", "budget", "role_head", "role_staff", "cm_phone", "cm_telegram", "cm_whatsapp", "submit"]


def translit_email(last: str, first: str, rnd: random.Random) -> str:
    table = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
                           "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
                           "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
                           "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"})
    domain = rnd.choice(["mail.ru", "yandex.ru", "gmail.com", "bk.ru"])
    return f"{first.lower().translate(table)}.{last.lower().translate(table)}@{domain}"


def make_lead(rnd: random.Random, services: list[dict]) -> tuple[dict, dict]:
    last, first, middle = rnd.choice(MALE if rnd.random() < 0.7 else FEMALE)
    niche = rnd.choice(NICHES)
    svc = rnd.choice(services)
    step = 1000 if svc["budget_max"] - svc["budget_min"] <= 200_000 else 5000
    budget = rnd.randrange(svc["budget_min"], svc["budget_max"] + 1, step)
    role = "руководитель" if niche == "Частный владелец" or rnd.random() < 0.55 else "сотрудник"
    contact = rnd.choice(CONTACT)
    comment = rnd.choice(COMMENTS)

    application = {
        "last_name": last,
        "first_name": first,
        "middle_name": middle if rnd.random() < 0.8 else None,
        "phone": f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
        "email": translit_email(last, first, rnd) if contact == "email" or rnd.random() < 0.5 else None,
        "service_id": svc["id"],
        "business_niche": niche,
        "company_size": rnd.choice(COMPANY_SIZE[niche]),
        "task_volume": "Разовая услуга" if niche == "Частный владелец" else rnd.choice(TASK_VOLUME),
        "role": role,
        "need_volume": rnd.choice(NEED_VOLUME[niche]),
        "deadline": rnd.choice(DEADLINES),
        "task_type": rnd.choice(TASK_TYPES),
        "product_interest": "Корпоративный договор" if niche == "Такси-парк" and rnd.random() < 0.6 else rnd.choice(INTEREST),
        "budget": str(budget),
        "contact_method": contact,
        "contact_time": rnd.choice(CONTACT_TIME),
        "comment": comment.format(car=rnd.choice(CARS)) if comment else None,
    }

    time_on_page = rnd.randint(40, 600)
    n_clicks = rnd.randint(3, 25)
    click_times = sorted(round(rnd.uniform(3, time_on_page - 1), 1) for _ in range(n_clicks))
    clicks = [{"el": rnd.choice(TRACKED[:-1]), "t": t} for t in click_times[:-1]] + [{"el": "submit", "t": click_times[-1]}]
    hovers = [{"el": rnd.choice(TRACKED), "ms": rnd.randint(500, 4500)} for _ in range(rnd.randint(1, 8))]
    utm = dict(rnd.choice(UTM))
    ua_idx = rnd.randrange(len(UA))
    metrics = {
        "time_on_page_sec": time_on_page,
        "clicks": clicks,
        "hovers": hovers,
        "return_count": rnd.choices([0, 1, 2, 3], weights=[50, 30, 15, 5])[0],
        "scroll_depth": rnd.randint(55, 100),
        "utm": utm,
        "referrer": REFERRERS.get(utm.get("utm_source", ""), None),
        "user_agent": UA[ua_idx],
        "screen": SCREENS[ua_idx],
        "language": "ru-RU",
    }
    return application, metrics


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=10, help="сколько заявок (по умолчанию 10)")
    ap.add_argument("--seed", type=int, default=None, help="зерно генератора для воспроизводимости")
    args = ap.parse_args()
    rnd = random.Random(args.seed)

    print(f"API: {base_url()}/api/applications")
    _, services = request("GET", "/api/admin-settings?only_active=true")
    if not services:
        raise SystemExit("Нет активных услуг — сначала создайте их в Swagger или: make seed")

    rows, ok = [], 0
    for _ in range(args.n):
        application, metrics = make_lead(rnd, services)
        svc_name = next(s["services"] for s in services if s["id"] == application["service_id"])
        fio = f'{application["last_name"]} {application["first_name"][0]}.'
        try:
            status, res = request("POST", "/api/applications", {"application": application, "metrics": metrics})
            ok += 1
            result = f'{status} #{res["id"]}'
        except ApiError as exc:
            result = f"ОШИБКА {exc.status}"
        rows.append([fio, application["business_niche"], svc_name, f'{int(application["budget"]):,}'.replace(",", " "),
                     application["role"], metrics["utm"].get("utm_source", "—"),
                     f'{metrics["time_on_page_sec"]} с', len(metrics["clicks"]), metrics["return_count"], result])

    print_table(["Клиент", "Ниша", "Услуга", "Бюджет ₽", "Роль", "UTM", "На стр.", "Кликов", "Возвр.", "Ответ"], rows)
    print(f"\nОтправлено успешно: {ok} из {args.n}")
    if ok != args.n:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
