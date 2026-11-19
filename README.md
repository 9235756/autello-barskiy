# Autello Barskiy — Кейс 3: сайт для обработки заказов

- **Часть 1** — инфраструктура: Nginx, PostgreSQL, pgAdmin, локальный Docker Registry с веб-интерфейсом, Watchtower.
- **Часть 2** (этот README) — backend на FastAPI, фронтенд в «элитном стиле», собранный webpack'ом, и их связка через Nginx.

Весь стек поднимается одной командой (`make all`). Он одинаково работает локально в Docker (`MOCK_MODE=true`) и на VPS с Ubuntu 22.04.

## Архитектура

```
                         браузер / Playwright / scripts/*.py
                                      │  :80
   ┌──────────────────────── сеть public ─────────────────────────────┐
   │  nginx ── /            → frontend/dist (index.html)              │
   │        ── /admin       → frontend/dist/admin/index.html          │
   │        ── /assets/*    → CSS/JS с contenthash, кеш на год        │
   │        ── /api/*       → backend:8000  (путь не переписывается)  │
   │        ── /docs        → backend:8000  только при DOCS_ENABLED   │
   │  pgadmin :5050   registry :5001   registry-ui :8080   watchtower │
   └───────────┬───────────────────────────────┬──────────────────────┘
               │ nginx и pgadmin — в обеих сетях
   ┌───────────┴──────── сеть internal (internal: true) ──────────────┐
   │  backend :8000 (без ports)  ──SQLAlchemy/psycopg──▶  postgres    │
   └──────────────────────────────────────────────────────────────────┘
```

- **Backend** находится только в сети `internal` и не публикует порты. Снаружи до него можно добраться только через nginx `/api/`.
- **Postgres** видят только `backend` и `pgadmin`.
- **Swagger** открыт временно, для тестирования. При `DOCS_ENABLED=false` nginx отвечает 404 на `/docs` и `/openapi.json`.

## Структура (новое в части 2)

```
backend/
├── Dockerfile               python:3.12-slim, uvicorn 0.0.0.0:8000, HEALTHCHECK → /api/health
├── requirements.txt         фиксированные версии
└── app/
    ├── main.py              FastAPI(redirect_slashes=False), роутеры с prefix="/api", create_all
    ├── core/config.py       настройки из env, DATABASE_URL собирается из POSTGRES_*
    ├── core/db.py           engine, SessionLocal, Base, get_db
    ├── models/              модель + SQL CREATE TABLE в docstring + класс CRUD в каждом файле
    │   ├── admin_settings.py     услуги и диапазоны цен
    │   ├── application.py        заявка (FK → admin_settings)
    │   └── behavior_metrics.py   метрики, 1:1 (application_id = PK и FK)
    ├── schemas/             Pydantic In/Out, from_attributes=True
    └── routers/             health, admin_settings, applications
frontend/
├── package.json, webpack.config.js    webpack 5 + mini-css-extract-plugin, publicPath "/"
└── src/
    ├── index.html, index.js           клиентская страница с формой
    ├── admin.html, admin.js           /admin: CRUD услуг + последние заявки
    ├── tracker.js                     поведенческие метрики
    ├── api.js                         fetch с таймаутом, только относительные /api/...
    └── styles/                        base.css, main.css, admin.css
nginx/templates/                       шаблоны → /etc/nginx/conf.d через envsubst
├── default.conf.template
├── docs/docs_true.conf.template       /docs и /openapi.json → backend
├── docs/docs_false.conf.template      /docs и /openapi.json → 404
└── snippets/                          proxy_params, security_headers
scripts/
├── seed_services.py       3 услуги через API (запасной путь, основной — Swagger)
├── simulate_leads.py      N клиентов с метриками → POST /api/applications
├── mock_gpt.py            заглушка GPT-анализа лида (для следующей части)
├── e2e/form.spec.ts       Playwright: форма → «Заявка отправлена!» + скриншоты
└── check.sh / check.ps1   9 групп проверок → reports/check_report.md
```

## Быстрый старт (эмуляция)

Нужны Docker Desktop или Docker Engine с плагином `docker compose`, а также `make` и `python3`. Node.js не обязателен: без него фронт соберётся в контейнере.

```bash
make all
```

Цепочка выполняет `init → ensure-user → build-front → up → seed → leads → e2e → check`. В конце должна появиться строка **«✅ Все проверки пройдены»**.

| Цель | Что делает |
|---|---|
| `make build-front` | `npm ci && npm run build` в `frontend/`, а если npm нет — `docker compose --profile tools run --rm frontend-build` |
| `make up` | `docker compose up -d --build` и ожидание, пока backend и nginx станут healthy |
| `make seed` | `python scripts/seed_services.py` — 3 услуги (идемпотентно) |
| `make leads` | `python scripts/simulate_leads.py` — 10 заявок (`-n 50` — больше) |
| `make e2e` | `docker compose --profile tools run --rm e2e` — браузерный тест и скриншоты |
| `make check` | `bash scripts/check.sh` → `reports/check_report.md` |
| `make logs` | `docker logs -f backend` (`make logs-nginx` — то же для nginx) |
| `make gpt` | мок-анализ трёх последних заявок |
| `make push` | собрать backend и отправить в локальный registry |

### Windows (PowerShell)

```powershell
if (-not (Test-Path .env)) { Copy-Item example.env .env }                          # init
# build-front: локальный npm или контейнер
if (Get-Command npm -ErrorAction SilentlyContinue) { Push-Location frontend; npm ci; npm run build; Pop-Location }
else { docker compose --profile tools run --rm frontend-build }
docker compose up -d --build                                                        # up
python scripts\seed_services.py                                                     # seed
python scripts\simulate_leads.py                                                    # leads
docker compose --profile tools run --rm e2e                                         # e2e
powershell -ExecutionPolicy Bypass -File scripts\check.ps1                          # check
docker logs -f backend                                                              # logs
```

Если файла `registry\auth\htpasswd` нет (свежий клон), создайте пользователя реестра так, как описано в разделе части 1 ниже.

## Что открыть

| Адрес | Что там |
|---|---|
| http://localhost/ | Клиентская страница: выбор услуги, ползунок бюджета, форма |
| http://localhost/admin | Админка: CRUD услуг и последние заявки (авторизация будет в следующем уроке) |
| http://localhost/docs | Swagger, если `DOCS_ENABLED=true` |
| http://localhost:5050 | pgAdmin: `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` |
| http://localhost:8080 | Registry UI |

В pgAdmin: **Servers → Autello → Autello PostgreSQL (internal)**, пароль — `POSTGRES_PASSWORD`. Дальше **autello → Schemas → public → Tables → applications**, правый клик → **View/Edit Data → All Rows**.

## Создание услуг вручную через Swagger (основной способ по заданию)

1. Откройте http://localhost/docs.
2. Раскройте **POST /api/admin-settings** и нажмите **Try it out**.
3. Вставьте JSON и нажмите **Execute**. Ожидаемый ответ — **201** с `id`, `created_at` и `updated_at`:
   ```json
   { "services": "Полировка кузова", "budget_range": "15к–60к", "budget_min": 15000, "budget_max": 60000 }
   ```
4. Повторите шаг для двух других услуг:
   ```json
   { "services": "Химчистка салона", "budget_range": "10к–40к", "budget_min": 10000, "budget_max": 40000 }
   { "services": "Керамическое покрытие", "budget_range": "50к–250к", "budget_min": 50000, "budget_max": 250000 }
   ```
   `budget_range` можно не передавать: он соберётся из `budget_min` и `budget_max`. Если услуга с таким названием уже есть, придёт ответ 409.
5. В **GET /api/admin-settings** нажмите **Try it out → Execute**. Ответ — список всех услуг.

Запасной вариант — `make seed`: скрипт создаёт те же три услуги и пропускает уже существующие.

## API

| Метод и путь | Ответ |
|---|---|
| `GET /api/health` | `{"status":"ok","db":"ok"}` (внутри — `SELECT 1`) |
| `GET /api/admin-settings` | весь список услуг (`?only_active=true` — только активные) |
| `POST /api/admin-settings` | 201 + услуга |
| `GET/PUT/DELETE /api/admin-settings/{id}` | услуга / изменённая услуга / 204 |
| `POST /api/applications` | 201 `{"id": 11, "message": "Заявка отправлена!"}` |
| `GET /api/applications?limit=50` | заявки вместе с метриками |
| `GET /api/applications/{id}` | заявка вместе с метриками |

Тело `POST /api/applications` — один пакет. Backend сохраняет его в одной транзакции: либо обе строки, либо ни одной.

```json
{
  "application": { "last_name": "Барский", "first_name": "Андрей", "phone": "+7 916 123-45-67",
                   "service_id": 3, "role": "руководитель", "budget": "180000", "contact_method": "telegram" },
  "metrics": { "time_on_page_sec": 312, "clicks": [{"el": "submit", "t": 311.4}],
               "hovers": [{"el": "service", "ms": 1830}], "return_count": 1, "scroll_depth": 100,
               "utm": {"utm_source": "yandex"}, "referrer": null, "user_agent": "...", "screen": "1920x1080", "language": "ru-RU" }
}
```

Каждый роут зарегистрирован дважды — с путём `""` и `"/"`. Поэтому `/api/applications` и `/api/applications/` отвечают одинаково, без 307.

## Что эмулируется

- **Внешних API-ключей задание не требует.** `OPENAI_API_KEY` в `.env` — заглушка для следующей части. `scripts/mock_gpt.py` при `MOCK_MODE=true` выдаёт `{lead_score, segment, summary}` по эвристике.
- **Клиенты и их поведение** — `simulate_leads.py`: русские ФИО, телефоны +7, ниши (автосалон, детейлинг, такси-парк, частник), бюджет в пределах диапазона услуги, 40–600 с на странице, 3–25 кликов, наведения курсора, 0–3 возврата, UTM yandex/vk/telegram. Заявки идут через nginx, поэтому проверяется вся цепочка «фронт → nginx → backend → Postgres».
- **Скриншоты для сдачи** делает Playwright в Docker (`make e2e`) и складывает в `reports/screens/`:
  - `01_home.png`, `02_filled.png`, `03_success.png` — главная, заполненная форма, «Заявка отправлена!»;
  - `04_admin.png` — админка;
  - `05_docs.png`, `06_docs_get_list.png` — Swagger и ответ GET со списком услуг.

## Типичные ошибки урока и их причины

| Симптом | Причина | Как сделано здесь |
|---|---|---|
| **CSS 404** или «Refused to apply style… MIME type text/html» | 1) `style-loader`: CSS вшит в JS, отдельного файла нет. 2) Относительный `publicPath`: на `/admin/` ссылка превращается в `/admin/assets/...` (или `/pgadmin/...`). 3) Неверный `root` или `location` в nginx. 4) `try_files ... /index.html` для статики: вместо отсутствующего CSS отдаётся HTML | `mini-css-extract-plugin`, `publicPath: "/"`, `root /usr/share/nginx/html` с примонтированным `frontend/dist`, у `/assets/` — `try_files $uri =404` |
| **405 Not Allowed** | `proxy_pass http://backend:8000/;` (со слэшем) срезает `/api/` → FastAPI не находит роут. Или POST попадает в `location /` и уходит в статику: nginx отвечает 405 на POST к файлу | `location /api/ { proxy_pass http://backend:8000; }` без слэша и без переписывания, роутеры с `prefix="/api"` |
| **307 Temporary Redirect** | FastAPI с `redirect_slashes=True` редиректит `/api/x/` → `/api/x` на внутренний адрес `http://backend:8000/...`, браузер туда не попадает. Тело POST при этом теряется | `redirect_slashes=False` и дубли путей `""` / `"/"` |
| **«Input should be a valid string»** после POST | В схеме ответа `id: str` или `created_at: str`, а модель отдаёт `int` и `datetime`. Pydantic 2 не приводит их к строке | Out-схемы: `id: int`, `created_at: datetime`, `from_attributes=True` |
| **Бесконечная загрузка услуг** | Фронт вызывает `/latest` (одна запись или 404) вместо списка, ошибка не обрабатывается, спиннер не гаснет | `GET /api/admin-settings` — весь список. На фронте таймаут 8 с, состояния «ошибка» с кнопкой «Повторить» и «услуг нет» |
| **`npm: command not found`** | На машине или VPS нет Node.js | `make build-front` сам переключается на контейнер `node:20-alpine` (профиль `tools`) |
| **502 после обновления backend** | nginx запомнил старый IP контейнера, а Watchtower пересоздал контейнер | `resolver 127.0.0.11 valid=10s` и адрес backend в переменной |

Где искать ошибки: `docker logs -f backend` (Traceback, 422 с текстом ошибки валидации), `docker logs -f nginx` (404/405/502, путь запроса) и итоговый конфиг `docker exec nginx cat /etc/nginx/conf.d/default.conf`.

## Деплой на VPS

Первичная настройка сервера (SSH-ключ, Docker, rsync) — в разделе «Часть 1» ниже. Для части 2 дополнительно:

1. В `.env` на сервере:
   - `MOCK_MODE=false`;
   - `DOCS_ENABLED=false` (или `true` на время проверки);
   - `CORS_ORIGINS=http://<IP-или-домен>`;
   - `REGISTRY_HOST=<IP-или-домен>`, `REGISTRY_PORT=5000`.
2. Соберите фронт: `make build-front` (на VPS без Node.js сработает контейнер) — или передайте готовый `frontend/dist` через rsync.
3. Первый запуск: `make up`, затем создайте услуги через Swagger или `make seed`.
4. **Обновление backend через registry и Watchtower:**
   ```bash
   # на машине разработчика (или прямо на VPS)
   make push        # docker login → docker compose build backend → docker compose push backend
   ```
   Watchtower проверяет реестр каждые `WATCHTOWER_POLL_INTERVAL` секунд. Найдя новый `autello-backend:latest`, он сам пересоздаёт контейнер `backend` (у него есть метка `com.centurylinklabs.watchtower.enable=true`). Postgres без метки, автоматически его не обновляем.
   - Для push по HTTP на `<IP>:5000` нужен `insecure-registries` или TLS — см. «TLS для реестра».
   - Локально (`REGISTRY_HOST=localhost`) Watchtower изнутри своего контейнера не видит `localhost:5001`, поэтому в его логе будут предупреждения о pull. На работу стека они не влияют.
5. Проверка на сервере: `ssh autello-vps 'cd /opt/autello_barskiy && bash scripts/check.sh'`.

## Чек-лист скриншотов для сдачи

1. Swagger с тремя услугами: `reports/screens/05_docs.png` (или скриншот после ручного POST).
2. Ответ GET со списком: `reports/screens/06_docs_get_list.png`.
3. Главная страница: `01_home.png`, заполненная форма: `02_filled.png`.
4. Сообщение «Заявка отправлена!»: `03_success.png`.
5. pgAdmin с таблицей `applications` (View/Edit Data) — снимите вручную, путь описан выше.
6. Терминал с `docker ps`: backend без опубликованных портов, nginx `0.0.0.0:80`.
7. `reports/check_report.md` с итогом «✅ Все проверки пройдены».

## Упаковка и GitHub

`.env`, `registry/auth/htpasswd`, `node_modules/`, `frontend/dist/`, `mock/` и `reports/` исключены в `.gitignore`. Если нужно показать сборку, уберите строку `frontend/dist/` из `.gitignore`. Если нужно показать отчёт и скриншоты, уберите `reports/`: паролей в них нет.

**Zip без секретов** (из папки над проектом):

```bash
zip -r Autello_Barskiy.zip Autello_Barskiy \
  -x 'Autello_Barskiy/.env' 'Autello_Barskiy/registry/auth/htpasswd' \
     '*/node_modules/*' 'Autello_Barskiy/mock/*' '*/.DS_Store'
# чтобы не включать сборку, добавьте: 'Autello_Barskiy/frontend/dist/*'
```

**GitHub:**

```bash
git add . && git status          # убедитесь, что .env, htpasswd и node_modules НЕ в списке
git commit -m "Autello: backend FastAPI + фронтенд + nginx (Кейс 3, часть 2)"
git push
```

---

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

Файрвол: `ufw allow OpenSSH; ufw allow 80,443,5000,5050,8080/tcp; ufw enable`. Docker публикует порты в обход ufw, поэтому главная защита — отсутствие `ports:` у postgres и backend.

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
| Таблицы части 2 не появились | Их создаёт backend при старте (`create_all`). Смотрите `docker logs backend` |

Таблица `leads` и скрипт `seed_leads.py` остались от части 1. Новая форма пишет в `applications` и `behavior_metrics`.
