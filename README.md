# Autello Barskiy — Кейс 3: сайт для обработки заказов

- **Часть 1** — инфраструктура: Nginx, PostgreSQL, pgAdmin, локальный Docker Registry с веб-интерфейсом, Watchtower.
- **Часть 2** — backend на FastAPI, фронтенд на webpack, связка через Nginx.
- **Часть 3** (этот README) — вход в админку по JWT, CRUD услуг в таблице, поведенческие метрики с heatmap, приоритизация лидов, HTTPS и защищённый режим.

Стек одинаково работает локально в Docker (`MOCK_MODE=true`) и без изменений на VPS с Ubuntu 22.04.

## Два режима запуска

Пункты 1–4 задания требуют Swagger на `:8000` и pgAdmin, а пункт 5 требует их закрыть. Поэтому режимов два:

| | `make dev` — разработка | `make secure` — защищённый (пункт 5) |
|---|---|---|
| Файлы compose | `docker-compose.yml` + `docker-compose.dev.yml`, профиль `admin-tools` | только `docker-compose.yml` (это и есть `docker compose up --build -d`) |
| Сайт | http://localhost и https://localhost | https://localhost; http → **301** на https |
| Swagger | http://localhost:8000/docs (backend на `127.0.0.1:8000`) и https://localhost/docs | `/docs`, `/openapi.json` → **404** |
| `:8000`, `:5432` | backend на `127.0.0.1:8000`, PostgreSQL не опубликован | nginx отвечает **403** на HTTP-запрос |
| pgAdmin `:5050`, registry `:5000`, UI `:8080` | работают | не запускаются: соединение отклонено |
| Порты наружу | nginx, backend (только loopback), pgAdmin, registry | **только nginx** |

> **Про «код 403» на 8000 и 5432.** Закрытый порт обычно просто отклоняет соединение (`Connection refused`), а не отвечает кодом 403. Чтобы требование выполнилось буквально, в защищённом режиме эти порты слушает **nginx** и на любой HTTP-запрос отвечает `403 Forbidden` (`nginx/templates/modes/secure.conf.template`). Настоящие backend и PostgreSQL наружу не опубликованы вообще: они сидят во внутренней docker-сети `internal` без выхода наружу. До них такие запросы не доходят.

> **Если порты 8000 или 5432 на вашей машине уже заняты** (другой контейнер, локальный PostgreSQL), задайте в `.env` другие: `BACKEND_DEV_PORT`, `STUB_BACKEND_PORT`, `STUB_POSTGRES_PORT`. На VPS оставьте 8000 и 5432.

## Быстрый старт: всё автоматически

Нужны Docker Desktop или Docker Engine с плагином `docker compose`, а также `make`, `python3` и `openssl`. Node.js не обязателен: без него фронт соберётся в контейнере.

```bash
make all
```

Цепочка: `secret → certs → dev → build-front → seed → test-sql → backfill → e2e → pytest → secure → check`. Займёт около 5 минут, из них 2,5 минуты — «живой» визит Playwright. В конце должна появиться строка **«✅ Все проверки пройдены»**, а в `reports/check_report.md` — таблица с ✅ по каждому пункту.

| Цель | Что делает |
|---|---|
| `make secret` | создаёт `.env` (если нет), дописывает новые переменные из `example.env`, генерирует `SECRET_KEY` (`openssl rand -hex 32`) |
| `make certs` | самоподписанный сертификат → `nginx/certs/` (CN=localhost, SAN с `VPS_DOMAIN`/`VPS_HOST`) |
| `make dev` | режим разработки (см. таблицу выше) |
| `make secure` | защищённый режим: останавливает pgAdmin/registry, `docker compose up --build -d` |
| `make build-front` | `npm ci && npm run build` в `frontend/`, а без npm — в контейнере `node:20-alpine` |
| `make seed` | 5 услуг через API с логином демо-админа (запасной путь, основной — таблица в админке) |
| `make test-sql` | `psql < sql/test_applications.sql` — 10 тестовых заявок (4 🔥 / 3 🌤 / 3 ❄️) |
| `make backfill` | ~300 исторических визитов за 30 дней в `behavior_metrics` |
| `make e2e` | Playwright в контейнере: 6 сценариев и скриншоты в `reports/screens/`. Короче: `make e2e VISIT_SECONDS=30`, один файл: `make e2e E2E_ARGS=ranking` |
| `make pytest` | `pytest` балльной системы внутри контейнера backend |
| `make check` | `scripts/check.sh` → `reports/check_report.md` |
| `make logs` | `docker logs -f backend` (`make logs-nginx` — то же для nginx) |

### Windows (PowerShell)

```powershell
# secret: .env и SECRET_KEY
if (-not (Test-Path .env)) { Copy-Item example.env .env }
$key = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
(Get-Content .env) -replace '^SECRET_KEY=.*', "SECRET_KEY=$key" | Set-Content -Encoding utf8 .env
# certs: самоподписанный сертификат (openssl в контейнере)
New-Item -ItemType Directory -Force nginx\certs | Out-Null
docker run --rm -v "${PWD}\nginx\certs:/certs" alpine:3 sh -c "apk add -q openssl && openssl req -x509 -nodes -newkey rsa:2048 -days 825 -keyout /certs/privkey.pem -out /certs/fullchain.pem -subj /CN=localhost -addext subjectAltName=DNS:localhost,IP:127.0.0.1"
# build-front
if (Get-Command npm -ErrorAction SilentlyContinue) { Push-Location frontend; npm ci; npm run build; Pop-Location } else { docker compose --profile tools run --rm frontend-build }
# dev
$env:COMPOSE_PROFILES = 'admin-tools'; docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build; Remove-Item Env:COMPOSE_PROFILES
python scripts\seed_services.py                                                            # seed
Get-Content sql\test_applications.sql -Raw | docker compose exec -T postgres psql -U autello -d autello   # test-sql
python scripts\backfill_metrics.py                                                         # backfill
docker compose exec -T postgres psql -U autello -d autello -c "DELETE FROM admins"         # (только для e2e на «чистой» БД)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile tools run --rm e2e   # e2e
docker compose run --rm --no-deps -T backend python -m pytest -q -p no:cacheprovider tests  # pytest
# secure
docker compose --profile admin-tools stop pgadmin registry registry-ui; docker compose --profile admin-tools rm -f pgadmin registry registry-ui
docker compose up --build -d
powershell -ExecutionPolicy Bypass -File scripts\check.ps1                                 # check
docker logs -f backend                                                                     # logs
```

## Работа в двух терминалах

| Терминал 1 — корень проекта | Терминал 2 — `frontend/` |
|---|---|
| `make dev` (или `docker compose up --build -d`) | `npm run build` после каждой правки в `src/` (`npm run dev` пересобирает сам) |
| `docker logs -f backend` — запросы, ошибки, Traceback | — |
| `docker compose up --build -d backend` — после правки Python | — |

Nginx раздаёт `frontend/dist` напрямую через volume, поэтому после `npm run build` достаточно обновить страницу с очисткой кеша: **Ctrl+F5** (на macOS — **Cmd+Shift+R**).

---

## Пункт 1. Админка: логин, пароль и JWT

**Как устроено**

- Таблица `admins` (`backend/app/models/admin.py`): `id`, `username` (unique), `hashed_password`, `created_at`. SQL — в docstring модели и в `sql/schema_part3.sql`.
- Пароли хешируются библиотекой **bcrypt напрямую**: passlib ломается на bcrypt 4.1+. JWT выдаёт **PyJWT** (HS256), ключ берётся из `SECRET_KEY`, срок — из `ACCESS_TOKEN_EXPIRE_MINUTES`.
- `GET /api/auth/check` → `{"has_admins": false}`. Пока админов нет, на странице входа видна кнопка **«Зарегистрироваться»**. После первой регистрации она исчезает, а повторный `POST /api/auth/register` получает **403**.
- `POST /api/auth/login` принимает **form-data** (`OAuth2PasswordRequestForm`), поэтому работает кнопка **Authorize** в Swagger.
- Под токеном: `POST/PUT/DELETE /api/admin-settings`, все `GET /api/applications*`, `GET /api/behavior-metrics*`. Публичные: `GET /api/admin-settings`, `POST /api/applications`, `POST /api/behavior-metrics`.
- Фронт хранит токен в `sessionStorage` (обёрнуто в `try/catch`). При любом 401 он показывает экран входа.

**Вручную**

1. `make dev`, откройте https://localhost/admin (или http://localhost/admin). Есть кнопка «Зарегистрироваться».
2. Зарегистрируйтесь, нажмите «Выйти» и убедитесь, что кнопки больше нет.
3. Swagger: http://localhost:8000/docs → **Authorize** → логин и пароль → **Authorize** → **Close**. Замок закрылся. Затем **GET /api/auth/me** → *Try it out* → *Execute* → **200**.

**Автоматически:** `make e2e`. Сценарий `e2e/admin_auth.spec.ts` проходит регистрацию, выход, проверку неверного пароля, «сломанный» токен и Swagger Authorize.

## Пункт 2. Услуги: таблица CRUD

**Вручную:** вкладка **«Услуги»** в админке. Справа — панель инструментов: **«Добавить строку»** и **«Обновить»**.

- **Добавить:** «Добавить строку» → заполнить поля прямо в таблице → «Сохранить» (или Enter).
- **Изменить:** кнопка «Изменить» или двойной щелчок по строке, затем «Сохранить» / Enter, отмена — Esc.
- **Удалить:** «Удалить» → подтверждение в **своём модальном окне** (не `window.confirm`). Услуга сразу пропадает из выпадающего списка на главной.

Создайте минимум 5 услуг, например:

| Услуга | От, ₽ | До, ₽ |
|---|---|---|
| Полировка кузова | 15 000 | 60 000 |
| Химчистка салона | 10 000 | 40 000 |
| Керамическое покрытие | 50 000 | 250 000 |
| Оклейка плёнкой PPF | 150 000 | 600 000 |
| Установка аудиосистемы Bose премиум | 80 000 | 500 000 |

Запасной путь — `make seed`: те же 5 услуг через API. Скрипт идемпотентен и входит как `DEMO_ADMIN_USER`.

**Автоматически:** `e2e/services_crud.spec.ts` добавляет 5 строк, правит одну, удаляет одну и проверяет, что на главной её больше нет.

## Пункт 3. Метрики и «Статистика пользователей»

**Как устроено**

- `frontend/src/behavior-metrics.js` на главной: `session_id` (`crypto.randomUUID`), счётчик секунд (только пока вкладка активна), клики по кнопкам и полям (по `data-track` или `id`/`name`), позиция курсора раз в секунду в долях 0..1 от размеров документа, `return_frequency` через `visibilitychange`.
- Раз в секунду, пока вкладка видима, уходит `POST /api/behavior-metrics` со снимком в формате урока:
  `{"application_id": 0, "time_on_page": 0, "buttons_clicked": "string", "cursor_positions": "string", "return_frequency": 0}` + `session_id`, `viewport_w/h`, `doc_w/h`, `page`. При закрытии страницы финальный снимок уходит через `navigator.sendBeacon`.
- Метрики **анонимные**: `application_id` принимается, но не проверяется (nullable, без FK и без UNIQUE). С `session_id` строка обновляется (upsert, одна строка на визит). `buttons_clicked` и `cursor_positions` хранятся в JSONB, а строка, которая не парсится, сохраняется как `{"raw": ...}`.
- Таблица части 2 (связь 1:1 с заявкой) мигрируется **автоматически при старте** backend: `sql/migrate_metrics_part3.sql` переименовывает её в `behavior_metrics_part2` и переносит данные в новый формат.
- Кнопка **«Статистика пользователей»** в админке открывает полноэкранное окно: три карточки (день/неделя/месяц — среднее, максимум, число сессий), heatmap курсора на canvas (сетка 40×40, круги поверх схемы страницы, размер и цвет зависят от частоты) и топ кликов.

**Вручную:** откройте главную и 2–3 минуты поводите мышью: выберите услугу, подвигайте ползунок, понажимайте поля, переключитесь на другую вкладку и вернитесь. Затем в админке нажмите «Статистика пользователей». Данные лежат в pgAdmin: http://localhost:5050 → **Servers → Autello → autello → Schemas → public → Tables → behavior_metrics** → правый клик → **View/Edit Data → All Rows**.

**Автоматически:**

- `make backfill` добавляет ~300 визитов за 30 дней (20–400 с, курсор кучкуется у поля услуги, ползунка и кнопки «Отправить»). Без истории средние за неделю и месяц были бы пустыми.
- `e2e/visitor_activity.spec.ts` запускает 3 виртуальных посетителей одновременно. Один проводит на странице `VISIT_SECONDS` (150 с): курсор плавно ходит по кривым Безье между элементами формы, есть клики по полям, ползунку и кнопкам и уход на другую вкладку. Второй смотрит 25 с, третий заполняет и отправляет форму. Тест проверяет рост строк `behavior_metrics` во время визита и снимает heatmap.

## Пункт 4. Приоритизация лидов

**Балльная система 0–100** (`backend/app/services/lead_scoring.py`, пороги вынесены в константы):

| Критерий | Максимум | Как считается |
|---|---|---|
| Бюджет | 30 | доля от `budget_max` услуги: ≥90% → 30, ≥70% → 24, ≥50% → 18, ≥30% → 10; бюджет ≥ 500 000 ₽ → 30 |
| Срок | 25 | как можно скорее 25 · неделя 18 · месяц 10 · не срочно 3 · не указан 5 |
| Размер компании | 15 | 200+ → 15 · 51–200 → 12 · 11–50 → 9 · 2–10 → 5 · только я → 2 |
| Роль | 10 | собственник / руководитель 10 · сотрудник 4 |
| Объём задачи | 10 | более 20 машин → 10 · 6–20 → 8 · регулярное обслуживание → 8 · 2–5 → 5 |
| Ниша | 10 | автосалон, такси-парк, премиум-частник (марка или бюджет ≥ 300 000 ₽) → 10 · детейлинг 8 |

**Температура:** 🔥 hot ≥ 70, 🌤 warm 40–69, ❄️ cold < 40. Кроме неё считаются `urgency`, `needs_personal_manager` (hot или бюджет ≥ 500 000 ₽), `department` (Корпоративный отдел / VIP-менеджер / Розничные продажи), `recommended_action` и `reasons[]` — почему заявка получила свой score. `LEAD_SCORING_MODE=llm_mock` добавляет «ИИ-резюме», которое собирается локально, без внешних вызовов.

**Эндпоинты:** `GET /api/applications/ranked` (по score), `GET /api/applications/{id}` (заявка + оценка + метрики визита), `GET /api/applications/summary` (по температурам, по услугам, средний бюджет, за 7 и 30 дней).

**10 тестовых заявок** — `sql/test_applications.sql`. Перед каждым блоком есть комментарий, почему заявка горячая или холодная:

| | Заявка | Score | Сильная сторона |
|---|---|---|---|
| 🔥 | Воронцов, Bentley, PPF 600 000 ₽ | 72 | огромный бюджет → VIP-менеджер |
| 🔥 | Кравцова, детейлинг-центр | 81 | срочно + руководитель |
| 🔥 | Шестаков, дилерский центр 200+ | 71 | крупный автосалон |
| 🔥 | Гусейнов, таксопарк 35 машин | 78 | большой объём (хотя пишет сотрудник) |
| 🌤 | Лаптева, Ершов, Миронова | 55 / 48 / 47 | |
| ❄️ | Пахомов, Зуева, Сидоренко | 32 / 24 / 15 | |

**Вручную:** pgAdmin → правый клик по БД **autello** → **Query Tool** → вставьте `sql/test_applications.sql` → **F5**. Нужны услуги из пункта 2. Затем в админке откройте вкладку **«Заявки»**: сверху общая статистика, ниже таблица по score с бейджами и фильтрами. **«Просмотр»** открывает окно со всеми полями, разбором score, причинами и ссылками `tel:` и `mailto:`.

**Автоматически:** `make test-sql`. `make pytest` (`backend/tests/test_lead_scoring.py`) читает тот же SQL-файл и проверяет ровно 4/3/3. `e2e/ranking.spec.ts` проверяет, что первые 4 строки — 🔥, и что «Просмотр» работает.

## Пункт 5. Безопасность

```bash
make secure            # = остановить pgAdmin/registry + docker compose up --build -d
make check             # блок «Безопасность (п.5)» в reports/check_report.md
```

Ручная проверка:

```bash
curl -kI https://localhost             # HTTP/2 200, strict-transport-security
curl -I  http://localhost              # 301 → https://localhost/
curl     http://localhost:8000         # 403 Forbidden (заглушка nginx)
curl     http://localhost:5432         # 403 Forbidden (заглушка nginx)
curl     http://localhost:5050         # Connection refused — pgAdmin выключен
curl -k  https://localhost/docs        # 404
docker ps                              # порты опубликованы только у nginx
```

- TLS: только 1.2 и 1.3, HTTP/2, HSTS (`max-age=31536000`, только в secure-режиме), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`.
- Сертификат: локально — самоподписанный (`make certs`), браузер покажет предупреждение, это ожидаемо. На VPS — Let's Encrypt, см. ниже.

### HTTPS на реальном VPS (Let's Encrypt)

1. Купите домен, A-запись → IP сервера. В `.env` на сервере: `VPS_DOMAIN=autello.ru`, `LETSENCRYPT_EMAIL=you@mail.ru`, `MOCK_MODE=false`.
2. `ufw allow 80,443/tcp`, затем `make certs && make secure` — стек поднимется с временным самоподписанным сертификатом.
3. `bash scripts/letsencrypt.sh`. Certbot в контейнере пройдёт проверку через `/.well-known/acme-challenge/` (nginx отдаёт её даже в secure-режиме), пропишет `SSL_CERT_PATH`/`SSL_KEY_PATH` в `.env` и перезапустит nginx.
4. Продление — cron: `0 3 * * 1 cd /opt/autello_barskiy && bash scripts/letsencrypt.sh --renew`.

## Пункт 6. Логи

```bash
docker logs -f backend      # запросы uvicorn, «Вход: admin», «Новая заявка #…», миграции при старте
docker logs -f nginx        # 301/403/404, пути запросов
docker exec nginx cat /etc/nginx/conf.d/default.conf   # итоговый конфиг после envsubst
```

---

## Что эмулируется и какие ключи нужны

- **Внешних сервисов с API в задании нет.** Нужны только собственные секреты: `SECRET_KEY` для JWT (`make secret`, внутри `openssl rand -hex 32`) и SSL-сертификат (`make certs` локально, Let's Encrypt на VPS). Всё описано в `example.env`.
- `OPENAI_API_KEY` — заглушка. `LEAD_SCORING_MODE=llm_mock` имитирует «ИИ-оценку» локально.
- **2–3 минуты живой активности** имитирует Playwright (`visitor_activity.spec.ts`). В headless-браузере нет настоящего переключения вкладок, поэтому «уход на другую вкладку» эмулируется событием `visibilitychange`, на которое реагирует трекер.
- **История метрик за месяц** — `scripts/backfill_metrics.py` (строки с `session_id` вида `backfill-…`, повторный запуск их пересоздаёт).
- `make e2e` при `MOCK_MODE=true` очищает таблицу `admins`, чтобы проверить кнопку «Зарегистрироваться» на «чистой» БД. Затем тест заново регистрирует демо-админа (`DEMO_ADMIN_USER` / `DEMO_ADMIN_PASSWORD`). На боевом сервере (`MOCK_MODE=false`) таблица не трогается.

## Новые и изменённые файлы части 3

```
backend/app/core/security.py        bcrypt + PyJWT
backend/app/core/deps.py            get_current_admin (OAuth2PasswordBearer tokenUrl=/api/auth/login)
backend/app/core/migrations.py      применение sql/*.sql при старте
backend/app/models/admin.py         admins + AdminCRUD (SQL в docstring)
backend/app/models/behavior_metrics.py   анонимные метрики, upsert, статистика и heatmap
backend/app/routers/auth.py         check / register / login / me
backend/app/routers/behavior_metrics.py  POST (публичный), GET и /stats (токен)
backend/app/routers/applications.py /ranked, /summary, /{id} с оценкой
backend/app/services/lead_scoring.py балльная система 0–100
backend/tests/test_lead_scoring.py  pytest: 10 заявок из SQL → 4/3/3
sql/schema_part3.sql                admins, behavior_metrics, CHECK роли
sql/migrate_metrics_part3.sql       миграция метрик части 2 → 3
sql/test_applications.sql           10 тестовых заявок
frontend/API.md                     шпаргалка по API (фронт сделан строго по ней)
frontend/src/behavior-metrics.js    метрики раз в секунду + sendBeacon
frontend/src/admin.*                вход, заявки, услуги, статистика
nginx/templates/modes/{dev,secure}.conf.template   режимы порта 80 и заглушки 403
nginx/templates/snippets/site.conf.template        сайт (общий для 80 и 443)
docker-compose.dev.yml              dev-режим поверх основного compose
e2e/*.spec.ts                       Playwright: 5 сценариев части 3 + регресс формы
scripts/gen_secret.sh, gen_selfsigned.sh, letsencrypt.sh, backfill_metrics.py, check.sh, check.ps1
```

## Типичные ошибки урока и как они решены

| Симптом | Причина | Как сделано здесь |
|---|---|---|
| **404 на `/api/auth/check`** | Лишний префикс: `proxy_pass http://backend:8000/api/;` превращает запрос в `/api/api/auth/check` | `location /api/ { proxy_pass http://backend:8000; }` без слэша и без URI. `check.sh` проверяет, что `/api/api/...` = 404, а `/api/auth/check` = 200 |
| **«Behavior metrics for application 0 already exists»** | В части 2 `application_id` был первичным ключом, а фронт и Swagger шлют `0` | `application_id` nullable, без FK и UNIQUE; один визит = одна строка по `session_id`. Миграция — при старте |
| **`ImportError: email-validator is not installed`** | `EmailStr` без `pydantic[email]` | В `requirements.txt` — `pydantic[email]` |
| **`AttributeError: module 'bcrypt' has no attribute '__about__'`** | passlib + bcrypt ≥ 4.1 | bcrypt напрямую, без passlib |
| **Таблица услуг пустая или падает `.map is not a function`** | Ответ не массив (ошибка, `/latest` вместо списка) | Фронт проверяет `Array.isArray`, при ошибке показывает текст в таблице |
| **Изменения фронта не видны** | Кеш браузера после `npm run build` | Ctrl+F5 / Cmd+Shift+R. Ассеты с `contenthash`, HTML с `Cache-Control: no-cache` |
| **Схема БД «поломалась» после экспериментов** | Таблицы создаются один раз (`create_all` не меняет существующие) | `docker compose stop backend` (иначе БД занята) → pgAdmin: правый клик по БД **autello** → **Delete** → **Create → Database** `autello`, владелец `autello` → `docker compose start backend`: таблицы создадутся заново. Или полностью: `make clean && make all` |
| **401 в Swagger** | Не нажата кнопка Authorize или истёк токен (120 мин) | Authorize → логин/пароль. Логин — form-data, не JSON |
| **307 / 405 на POST** | Слэш в конце или `proxy_pass` со слэшем | `redirect_slashes=False`, каждый роут с `""` и `"/"` |
| **nginx не стартует: `cannot load certificate`** | Нет сертификата | `make certs` перед первым запуском |

## Чек-лист скриншотов для сдачи

Автоматические (`make e2e`) лежат в `reports/screens/`:

| Файл | Что на нём | Пункт |
|---|---|---|
| `login_with_register.png` | вход на чистой БД, есть «Зарегистрироваться» | 1 |
| `login_without_register.png` | после регистрации кнопки нет | 1 |
| `swagger_authorized.png` | Swagger: Authorize, `GET /api/auth/me` → 200 | 1 |
| `services_table.png` | таблица услуг с панелью инструментов справа | 2 |
| `home_service_list.png` | список услуг на главной без удалённой | 2 |
| `stats_modal_heatmap.png` | «Статистика пользователей»: периоды, heatmap, топ кликов | 3 |
| `applications_ranked.png` | заявки по приоритету, сводка сверху | 4 |
| `application_details.png` | «Просмотр»: детали, причины, tel:/mailto: | 4 |

Снять вручную:

1. pgAdmin: `behavior_metrics` → View/Edit Data (пункт 3) и Query Tool с `sql/test_applications.sql` (пункт 4).
2. Терминал: `make secure` и `curl` из пункта 5 (301, 403, 404, `Connection refused`), а также `docker ps`.
3. Терминал: `docker logs -f backend` (пункт 6).
4. `reports/check_report.md` с итогом «✅ Все проверки пройдены».

## Упаковка и GitHub

`.env`, `nginx/certs/` (ключи TLS), `registry/auth/htpasswd`, `node_modules/`, `frontend/dist/`, `mock/` и `reports/` исключены в `.gitignore`. Чтобы показать отчёт и скриншоты, уберите строку `reports/` — паролей в них нет.

**Zip без секретов** (из папки над проектом):

```bash
zip -r Autello_Barskiy.zip Autello_Barskiy \
  -x 'Autello_Barskiy/.env' 'Autello_Barskiy/nginx/certs/*' 'Autello_Barskiy/registry/auth/htpasswd' \
     '*/node_modules/*' 'Autello_Barskiy/mock/*' '*/.DS_Store' '*/__pycache__/*'
```

PowerShell:

```powershell
$files = git ls-files; Compress-Archive -Path $files -DestinationPath ..\Autello_Barskiy.zip   # только то, что в git
```

**GitHub:**

```bash
git add . && git status          # .env, nginx/certs, htpasswd и node_modules НЕ должны быть в списке
git commit -m "Autello: JWT, услуги, метрики, приоритизация, HTTPS (Кейс 3, часть 3)"
git push
```

---

## Часть 2: справка

- **API части 2 не сломан:** `POST /api/applications` по-прежнему принимает пакет `{"application": {...}, "metrics": {...}}`, `scripts/simulate_leads.py` работает. Новое: необязательный `session_id`, а метрики формата части 2 сохраняются отдельной строкой в `behavior_metrics`.
- `e2e/form.spec.ts` — регресс формы части 2 (скриншоты `01_home`–`03_success`).
- Создание услуг через Swagger: **Authorize** → **POST /api/admin-settings** → *Try it out* → JSON `{"services": "Полировка кузова", "budget_min": 15000, "budget_max": 60000}` → **201**.

## Часть 1: инфраструктура (справка)

### Цели Makefile из части 1

```bash
make init       # .env из example.env (если .env ещё нет)
make mock-vps   # «арендовать» VPS: mock/vps_instance.json
make user       # пользователь реестра в registry/auth/htpasswd
make down       # остановить
make clean      # остановить и удалить тома (БД, реестр) и артефакты
```

Пользователь реестра без bash (Windows):

```powershell
$e = @{}; Get-Content .env | ? { $_ -match '^[^#].*=' } | % { $k,$v = $_ -split '=',2; $e[$k]=$v }
docker run --rm httpd:2 htpasswd -Bbn $e.REGISTRY_USER $e.REGISTRY_PASSWORD | Set-Content -Encoding ascii registry\auth\htpasswd
```

### Реальный VPS

1. **Аренда.** ihor.online или reg.ru: «Виртуальные серверы» → Ubuntu 22.04. IP, пользователь `root` и пароль будут в разделе «Инструкция».
2. **Заполнить `.env`:** `MOCK_MODE=false`, `VPS_HOST`, `REGISTRY_HOST`, `REGISTRY_PORT=5000`, надёжные пароли.
3. **SSH по ключу:** `bash scripts/setup_ssh_key.sh`. Скрипт копирует ключ, проверяет вход и только после этого отключает вход по паролю.
4. **Docker:** `bash scripts/install_docker.sh` — Docker CE и `docker-compose-plugin` из официального репозитория.
5. **Деплой:** `bash scripts/deploy_to_vps.sh` — rsync в `/opt/autello_barskiy` и `docker compose up -d`.

Файрвол: `ufw allow OpenSSH; ufw allow 80,443/tcp; ufw enable` (в части 3 наружу нужен только nginx; порты 5000/5050/8080 открывайте лишь на время dev-режима). Docker публикует порты в обход ufw, поэтому главная защита — отсутствие `ports:` у postgres и backend.

### TLS для реестра

Docker без TLS разрешает push только на `localhost`. Чтобы пушить на `http://<IP>:5000`:

1. **Для учёбы — `insecure-registries`.** Docker Desktop: Settings → Docker Engine. Linux: `/etc/docker/daemon.json`:
   ```json
   { "insecure-registries": ["203.0.113.10:5000"] }
   ```
   Минус: логин и пароль идут открытым текстом.
2. **Рекомендуется — реестр за nginx с TLS (Let's Encrypt).** Нужен домен с A-записью на VPS. В nginx добавляется `server { listen 443 ssl; ... location /v2/ { proxy_pass http://registry:5000; } }`, а у `registry` убирается `ports:`.

### Частые проблемы

| Симптом | Решение |
|---|---|
| `bind: address already in use` на 5000 (macOS) | AirPlay Receiver. Используйте `REGISTRY_PORT=5001` |
| `docker-compose: command not found` | Используйте `docker compose` (плагин v2+) |
| pgAdmin: «email address is not valid» | Домен `.local` pgAdmin не принимает |
| Watchtower: `client version 1.25 is too old` | Нужен `nickfedor/watchtower`, а не `containrrr/watchtower` |
| nginx не стартует: `open() ".../docs_xxx.conf" failed` | `DOCS_ENABLED` должен быть строго `true` или `false` |
| Порт 8000 на хосте отвечает | Это другой процесс или контейнер. Backend стека порт не публикует, `check.sh` укажет владельца |
| Таблицы не появились | Их создаёт backend при старте (миграция → `create_all` → `sql/schema_part3.sql`). Смотрите `docker logs backend` |

Таблица `leads` и скрипт `seed_leads.py` остались от части 1. Новая форма пишет в `applications` и `behavior_metrics`.
