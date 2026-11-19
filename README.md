# Autello — Кейс 3: сайт для обработки заказов, часть 1

Инфраструктура MVP в виде «докеризированного монолита»: Nginx, PostgreSQL, pgAdmin, локальный Docker Registry с веб-интерфейсом и Watchtower. Backend появится в части 2. Сейчас в `docker-compose.yml` есть только закомментированная заготовка для него.

Один и тот же код работает в двух режимах:

| Режим | `MOCK_MODE` | Что происходит |
|---|---|---|
| **А. Эмуляция** | `true` | Аренда VPS подменена скриптом `mock_vps.py`, весь стек работает в локальном Docker |
| **Б. Боевой** | `false` | Скрипты настраивают SSH на реальном VPS Ubuntu 22.04, ставят Docker и разворачивают стек |

## Архитектура

```
                  Интернет / браузер
                         │
   ┌───────────── сеть public ─────────────────────────────┐
   │  nginx :80      registry :5001*   registry-ui :8080   │
   │  pgadmin :5050  watchtower (docker.sock)              │
   └───────────────────────┬───────────────────────────────┘
                           │ pgadmin стоит в обеих сетях
   ┌──────── сеть internal (internal: true) ───────────────┐
   │  postgres :5432 (не публикуется)   [backend — часть 2]│
   └───────────────────────────────────────────────────────┘
   * На macOS порт 5000 занят AirPlay Receiver, поэтому 5001. На VPS можно 5000.
```

- Снаружи доступны только Nginx, Registry (с логином), Registry UI и pgAdmin.
- PostgreSQL не публикует порт. Он находится в сети `internal`, у которой нет выхода наружу.
- Будущий backend будет доступен только через nginx (`location /api/`, пока закомментирован).
- Watchtower обновляет только контейнеры с меткой `com.centurylinklabs.watchtower.enable=true`. Postgres без этой метки, автоматически его не обновляем.
- Watchtower запускается из образа **`nickfedor/watchtower`**. Оригинальный `containrrr/watchtower` заархивирован 17.12.2025 на версии 1.7.1, а встроенный в него Docker SDK (API 1.25) не работает с Docker Engine 29+.

## Структура

```
Autello_Barskiy/
├── docker-compose.yml        стек из 6 сервисов + заготовка backend
├── example.env               шаблон переменных → .env
├── Makefile                  init, mock-vps, user, up, seed, check, down, clean, all
├── nginx/conf.d/default.conf фронт; /api/ → backend:8000 (закомментировано)
├── nginx/html/index.html     форма заявки + сбор лид-метрик в JSON
├── postgres/init/01_schema.sql  таблица leads
├── pgadmin/servers.json      сервер Postgres заранее прописан в pgAdmin
├── registry/config.yml       конфиг Registry v2
├── registry/create-user.sh   создание/обновление пользователя реестра (htpasswd)
├── scripts/
│   ├── mock_vps.py           эмулятор хостинга (раздел «Инструкция»)
│   ├── setup_ssh_key.sh      SSH-ключ, отключение входа по паролю
│   ├── install_docker.sh     Docker CE + docker compose plugin (Ubuntu 22.04)
│   ├── seed_leads.py         25 тестовых заявок автобизнеса в БД
│   ├── check.sh / check.ps1  проверка стека → reports/check_report.md
│   └── deploy_to_vps.sh      rsync на VPS + docker compose up -d
└── mock/, reports/           генерируются автоматически (в .gitignore)
```

## Сценарий А — эмуляция (≈5 минут)

Нужны Docker Desktop (или Docker Engine) с плагином `docker compose`, `make` и `python3`.

```bash
make all
```

Эта команда последовательно выполняет `init → mock-vps → user → up → seed → check`. В конце должна появиться строка `✅ Все проверки пройдены`.

Перед сдачей замените пароли в `.env`, затем выполните `make user` и `docker compose up -d`.

Что открыть:

| Адрес | Что там | Логин |
|---|---|---|
| http://localhost | Форма заявки. После отправки на странице и в консоли браузера появится JSON | — |
| http://localhost:8080 | Registry UI с образом `hello-world:test` | `REGISTRY_USER` / `REGISTRY_PASSWORD` |
| http://localhost:5001/v2/_catalog | API реестра (запросит логин) | то же |
| http://localhost:5050 | pgAdmin | `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` |

В pgAdmin: **Servers → Autello → Autello PostgreSQL (internal)**. Пароль — `POSTGRES_PASSWORD` из `.env`. Дальше **autello → Schemas → public → Tables → leads**, правый клик → **View/Edit Data → All Rows**.

> `pgadmin/servers.json` заполнен под имена по умолчанию (`autello`). Если меняете `POSTGRES_DB` или `POSTGRES_USER`, поправьте их и в этом файле.

### Отдельные цели

```bash
make init       # .env из example.env (если .env ещё нет)
make mock-vps   # «арендовать» VPS: mock/vps_instance.json
make user       # пользователь реестра в registry/auth/htpasswd
make up         # docker compose up -d + ожидание healthy postgres
make seed       # 25 заявок в leads (python3 scripts/seed_leads.py -n 100 — больше)
make check      # проверка + reports/check_report.md
make down       # остановить
make clean      # остановить и удалить тома (БД, реестр) и артефакты
```

### Windows (PowerShell)

```powershell
if (-not (Test-Path .env)) { Copy-Item example.env .env }                     # init
python scripts\mock_vps.py                                                     # mock-vps
$e = @{}; Get-Content .env | ? { $_ -match '^[^#].*=' } | % { $k,$v = $_ -split '=',2; $e[$k]=$v }
bash registry/create-user.sh $e.REGISTRY_USER $e.REGISTRY_PASSWORD             # user (Git Bash / WSL)
docker compose up -d                                                           # up
python scripts\seed_leads.py                                                   # seed
powershell -ExecutionPolicy Bypass -File scripts\check.ps1                     # check
docker compose down                                                            # down
```

Если bash нет, пользователя реестра можно создать без него:

```powershell
docker run --rm httpd:2 htpasswd -Bbn $e.REGISTRY_USER $e.REGISTRY_PASSWORD | Set-Content -Encoding ascii registry\auth\htpasswd
```

## Сценарий Б — реальный VPS

1. **Аренда.** На ihor.online или reg.ru: «Виртуальные серверы» → создать сервер с Ubuntu 22.04. В разделе «Инструкция» будут IP, пользователь `root` и пароль.
2. **Заполнить `.env`:**
   - `MOCK_MODE=false`;
   - `VPS_HOST` — IP сервера;
   - `REGISTRY_HOST` — IP или домен сервера;
   - `REGISTRY_PORT=5000`;
   - надёжные пароли.
3. **SSH по ключу:** `bash scripts/setup_ssh_key.sh`. Скрипт один раз спросит пароль root, скопирует ключ и проверит вход по нему. Только после успешной проверки он выключит `PasswordAuthentication` и выставит `PermitRootLogin prohibit-password`. Затем добавит `Host autello-vps` в `~/.ssh/config`.
4. **Docker:** `bash scripts/install_docker.sh`. Ставит Docker CE и `docker-compose-plugin` из официального репозитория Docker. Старый `docker-compose` v1 и `docker.io` удаляются. Если всё уже установлено, повторный запуск ничего не меняет.
5. **Деплой:** `bash scripts/deploy_to_vps.sh`. Делает rsync в `/opt/autello_barskiy`, создаёт пользователя реестра на сервере и выполняет `docker compose up -d`.
6. **Проверка на сервере:** `ssh autello-vps 'cd /opt/autello_barskiy && bash scripts/check.sh'`.

Рекомендуется закрыть всё лишнее файрволом: `ufw allow OpenSSH; ufw allow 80,443,5000,5050,8080/tcp; ufw enable`. Docker публикует порты в обход ufw, поэтому главная защита — то, что у postgres в compose нет `ports:`.

### TLS для реестра (важно)

Docker без TLS разрешает push только на `localhost`. Чтобы пушить с вашей машины на `http://<IP>:5000`, есть два пути:

1. **Быстро, для учёбы — insecure-registries.** В Docker Desktop: Settings → Docker Engine. В Linux: `/etc/docker/daemon.json`, затем `systemctl restart docker`.

   ```json
   { "insecure-registries": ["203.0.113.10:5000"] }
   ```

   Минус: логин и пароль реестра передаются открытым текстом (Basic Auth по HTTP).

2. **Рекомендуется — реестр за nginx с TLS (Let's Encrypt).**
   - Нужен домен с A-записью на VPS, например `registry.example.ru`.
   - Сертификат получаем через `certbot` (контейнер или пакет).
   - В nginx добавляем `server { listen 443 ssl; server_name registry.example.ru; client_max_body_size 0; location /v2/ { proxy_pass http://registry:5000; ... } }`.
   - У `registry` убираем `ports:`. Тогда реестр доступен только через nginx по HTTPS, `insecure-registries` не нужен, а пароли защищены шифрованием.

## Как устроены ключевые моменты

- **`registry/create-user.sh`** генерирует bcrypt-хэш через `docker run --rm httpd:2 htpasswd -Bbn`, поэтому на хост ничего ставить не нужно. Скрипт всегда пишет в `registry/auth/htpasswd` рядом с собой: второй копии файла не появится, из какой бы папки его ни запустили. Старая строка пользователя заменяется атомарно, без дублей. Если registry уже запущен, скрипт перезапускает его.
- **Форма (`index.html`)** собирает заявку и лид-метрики в один JSON:
  - UTM-метки, referrer, страница входа;
  - время заполнения и время на странице;
  - user-agent, язык, разрешение экрана, часовой пояс.

  Пока backend нет, JSON показывается на странице и пишется в `console.log` с пометкой «будет отправлено в POST /api/leads». Проверить можно так: http://localhost/?utm_source=yandex&utm_medium=cpc.
- **Таблица `leads`** повторяет поля формы. Метрики и техданные хранятся в `JSONB` (`metrics`, `tech_info`).
- **Слэши в nginx.** `location /api/` + `proxy_pass http://backend:8000/api/` передаёт путь как есть. А `proxy_pass http://backend:8000/` срежет префикс `/api/`. Подробнее — в комментарии в `default.conf`.

## Чек-лист скриншотов для сдачи

1. Дерево файлов проекта в редакторе (VS Code, панель Explorer).
2. Терминал с `docker ps`: 6 контейнеров `Up`, у postgres нет `0.0.0.0:5432`.
3. Registry UI (http://localhost:8080) с репозиторием `hello-world` и тегом `test`.
4. Окно входа в реестр или `curl` с кодами 401 (без логина) и 200 (с логином).
5. pgAdmin: таблица `leads` с данными (View/Edit Data).
6. Сайт http://localhost: форма и собранный JSON после отправки.
7. `reports/check_report.md` с итогом «✅ Все проверки пройдены».

## Упаковка и GitHub

Секреты (`.env`, `registry/auth/htpasswd`) и артефакты (`mock/`, `reports/`) уже исключены в `.gitignore`.

**Zip без секретов** (из папки над проектом):

```bash
zip -r Autello_Barskiy.zip Autello_Barskiy \
  -x 'Autello_Barskiy/.env' 'Autello_Barskiy/registry/auth/htpasswd' \
     'Autello_Barskiy/mock/*' 'Autello_Barskiy/.DS_Store' '*/.DS_Store'
```

Если нужно показать отчёт, уберите `reports/` из исключений: в нём нет паролей. Windows: `git archive` (ниже) или «Отправить → Сжатая ZIP-папка», предварительно удалив `.env` и `htpasswd` из копии.

**GitHub:**

```bash
git init && git add . && git status   # убедитесь, что .env и htpasswd НЕ в списке
git commit -m "Autello: инфраструктура MVP, часть 1"
git branch -M main
git remote add origin git@github.com:<user>/autello-barskiy.git
git push -u origin main
# zip из git (только отслеживаемые файлы): git archive -o Autello_Barskiy.zip HEAD
```

## Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `bind: address already in use` на 5000 (macOS) | AirPlay Receiver. Используйте `REGISTRY_PORT=5001` или отключите его в System Settings → General → AirDrop & Handoff |
| `docker-compose: command not found` или странные ошибки синтаксиса | Используйте `docker compose` (плагин v2+), а не `docker-compose` v1 |
| pgAdmin: «email address is not valid» | Домен `.local` pgAdmin не принимает. Укажите обычный email |
| Изменения в `postgres/init/*.sql` не применились | Init-скрипты выполняются только на пустом томе: `make clean && make up` |
| `failed to resolve reference ... EOF` при pull | Временный сбой Docker Hub. Повторите; `check.sh` делает до 3 попыток сам |
| Watchtower падает с `client version 1.25 is too old` | Используется старый `containrrr/watchtower`. Нужен `nickfedor/watchtower` |
