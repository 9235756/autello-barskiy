# API Autello — шпаргалка для фронтенда (часть 3)

Фронт обращается к API **только по относительным путям `/api/...`**: тот же хост, с которого открыта страница. Дальше nginx проксирует `location /api/` на `backend:8000` **без переписывания пути**. Префикс `/api` уже есть в путях бэкенда, поэтому `/api/api/...` не бывает.

Каждый путь работает и со слэшем на конце, и без него, без редиректа 307.

## Авторизация

| | |
|---|---|
| Схема | OAuth2 password → JWT (HS256), заголовок `Authorization: Bearer <token>` |
| Время жизни | `ACCESS_TOKEN_EXPIRE_MINUTES` (по умолчанию 120 мин) |
| Где хранить | `sessionStorage['autello_token']`. Обращение оборачивать в `try/catch`: в приватном режиме хранилище может быть недоступно |
| 401 на любом защищённом запросе | Удалить токен и показать экран входа |

| Метод и путь | Доступ | Тело запроса | Ответ |
|---|---|---|---|
| `GET /api/auth/check` | публичный | — | `{"has_admins": false}` |
| `POST /api/auth/register` | публичный, только пока админов нет | JSON `{"username": "admin", "password": "минимум 8 символов"}` | **201** `{"id", "username", "created_at"}`; если админ уже есть — **403** |
| `POST /api/auth/login` | публичный | **form-urlencoded** `username=…&password=…` (не JSON!) | `{"access_token", "token_type": "bearer", "expires_in": 7200}`; неверные данные — **401** |
| `GET /api/auth/me` | токен | — | `{"id", "username", "created_at"}` |

`username`: 3–50 символов, латиница, цифры и `_ . @ -`. `password`: 8–72 символа (ограничение bcrypt — 72 байта).

## Услуги — `admin_settings`

| Метод и путь | Доступ | Ответ |
|---|---|---|
| `GET /api/admin-settings` | публичный | **массив** услуг (`?only_active=true` — только активные, для главной) |
| `GET /api/admin-settings/{id}` | публичный | одна услуга |
| `POST /api/admin-settings` | токен | **201** + услуга; такое название уже есть — **409** |
| `PUT /api/admin-settings/{id}` | токен | изменённая услуга. Можно прислать только изменённые поля |
| `DELETE /api/admin-settings/{id}` | токен | **204** без тела |

Услуга (`AdminSettingsOut`):

```json
{ "id": 1, "services": "Полировка кузова", "budget_range": "15к–60к",
  "budget_min": 15000, "budget_max": 60000, "is_active": true,
  "created_at": "2026-11-19T10:00:00Z", "updated_at": "2026-11-19T10:00:00Z" }
```

Создание: `{"services", "budget_min", "budget_max", "budget_range"?, "is_active"?}`. Если `budget_range` не передан, бэкенд соберёт его из границ. Условие `budget_min ≤ budget_max` проверяется и на фронте, и на бэкенде (иначе **422**).

> Ответ списка — всегда массив. Перед `.map` проверять `Array.isArray(data)`: если пришёл объект ошибки, таблица не должна падать.

## Заявки — `applications`

| Метод и путь | Доступ | Ответ |
|---|---|---|
| `POST /api/applications` | публичный | **201** `{"id": 11, "message": "Заявка отправлена!"}` |
| `GET /api/applications?limit=50&offset=0` | токен | массив заявок (новые сверху) |
| `GET /api/applications/ranked` | токен | массив заявок с полем `scoring`, по `score` по убыванию. Фильтр `?temperature=hot\|warm\|cold` |
| `GET /api/applications/summary` | токен | сводка, см. ниже |
| `GET /api/applications/{id}` | токен | заявка + `scoring` + `metrics` визита (или `null`) |

Тело `POST /api/applications`:

```json
{ "application": { "last_name": "Барский", "first_name": "Андрей", "phone": "+7 916 123-45-67",
                   "service_id": 3, "role": "руководитель", "budget": "180000", "...": "..." },
  "session_id": "8c0f…-uuid визита из behavior-metrics.js",
  "metrics": { "time_on_page_sec": 312, "clicks": [], "...": "формат части 2, необязателен" } }
```

`role`: `сотрудник` | `руководитель` | `собственник`.

Поле `scoring` (балльная система `app/services/lead_scoring.py`):

```json
{ "score": 81, "temperature": "hot", "temperature_label": "🔥 горячий",
  "urgency": "высокая", "needs_personal_manager": true,
  "department": "VIP-менеджер", "recommended_action": "Написать в Telegram в течение 15 минут…",
  "reasons": ["Срок «Как можно скорее»: +25", "Бюджет 200 000 ₽ — 80% от максимума услуги: +24", "…"],
  "breakdown": {"budget": 24, "deadline": 25, "company": 9, "role": 10, "volume": 5, "niche": 8},
  "engine": "rules", "ai_summary": null }
```

`temperature`: `hot` (score ≥ 70), `warm` (40–69), `cold` (< 40). Бейджи на фронте: 🔥 горячий / 🌤 тёплый / ❄️ холодный.

Сводка `GET /api/applications/summary`:

```json
{ "total": 24, "by_temperature": {"hot": 6, "warm": 9, "cold": 9},
  "by_service": [{"service": "Керамическое покрытие", "count": 7}],
  "avg_budget": 143500, "last_7_days": 12, "last_30_days": 24,
  "needs_personal_manager": 7, "avg_score": 51.3 }
```

## Поведенческие метрики — `behavior_metrics`

| Метод и путь | Доступ | Ответ |
|---|---|---|
| `POST /api/behavior-metrics` | публичный | **201** + сохранённая строка |
| `GET /api/behavior-metrics?skip=0&limit=100` | токен | массив визитов |
| `GET /api/behavior-metrics/stats` | токен | статистика для модального окна |

Тело `POST` повторяет формат урока, остальные поля необязательны:

```json
{ "application_id": 0, "time_on_page": 37,
  "buttons_clicked": "{\"service\":2,\"submit\":1}",
  "cursor_positions": "[{\"x\":0.41,\"y\":0.21},{\"x\":0.44,\"y\":0.24}]",
  "return_frequency": 1,
  "session_id": "uuid", "viewport_w": 1366, "viewport_h": 900, "doc_w": 1366, "doc_h": 3380, "page": "/" }
```

- Главная шлёт **накопленный снимок** раз в секунду, пока вкладка активна. Последний снимок уходит через `navigator.sendBeacon` на `pagehide`. С `session_id` строка обновляется (upsert), поэтому на один визит приходится одна строка.
- `application_id` бэкенд не проверяет: внешнего ключа нет, поэтому ошибки «already exists» не бывает.
- `cursor_positions` — координаты в долях документа (0..1). Пиксели бэкенд тоже примет и нормализует, если передан `doc_w`/`doc_h` или `viewport_w`/`viewport_h`.
- Ошибки сети фронт молча игнорирует.

Ответ `GET /api/behavior-metrics/stats`:

```json
{ "periods": { "day":   {"avg_sec": 94.2, "max_sec": 380, "sessions": 14},
               "week":  {"avg_sec": 101.7, "max_sec": 398, "sessions": 82},
               "month": {"avg_sec": 99.0, "max_sec": 400, "sessions": 304} },
  "heatmap": [ {"x": 0.4125, "y": 0.2125, "count": 812} ],
  "top_buttons": [ {"name": "service", "count": 560} ],
  "grid": 40, "page_aspect": 2.47, "total_sessions": 304, "generated_at": "…" }
```

`heatmap` — сетка 40×40. `x`, `y` — центры ячеек в долях ширины и высоты документа. `page_aspect` — средняя пропорция высоты документа к его ширине, по ней строится силуэт страницы.

## Коды ошибок

| Код | Когда | Что делает фронт |
|---|---|---|
| 401 | нет токена, токен истёк или неверен | выход на экран входа |
| 403 | повторная регистрация | скрыть кнопку «Зарегистрироваться», показать сообщение |
| 404 | нет записи | сообщение в таблице или модалке |
| 409 | дубль названия услуги | сообщение у формы |
| 422 | ошибка валидации, `detail` — массив `{loc, msg}` | склеить в текст (`api.js → detailToText`) |
