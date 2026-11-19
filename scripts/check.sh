#!/usr/bin/env bash
# Проверка стека (часть 2: backend + nginx + фронт) → reports/check_report.md
#   bash scripts/check.sh      (или make check)
set -uo pipefail
source "$(dirname "$0")/_env.sh"

REPORT="reports/check_report.md"
mkdir -p reports
BASE="http://localhost$([ "${HTTP_PORT:-80}" = 80 ] || echo ":$HTTP_PORT")"
PORT_INT="${BACKEND_INTERNAL_PORT:-8000}"
PASS=0; FAIL=0
ROWS=()

ok()   { PASS=$((PASS+1)); ROWS+=("| ✅ | $1 | $2 |"); printf '\033[32m✅ %s\033[0m — %s\n' "$1" "$2"; }
bad()  { FAIL=$((FAIL+1)); ROWS+=("| ❌ | $1 | $2 |"); printf '\033[31m❌ %s\033[0m — %s\n' "$1" "$2"; }
check(){ if [ "$1" = 0 ]; then ok "$2" "$3"; else bad "$2" "$3"; fi; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@" || true; }
md()   { tr '|\n' '/ ' <<<"$1" | cut -c1-160; }   # безопасно для ячейки markdown-таблицы

echo "=== 1. Контейнеры ==="
COMPOSE_PS="$(docker compose ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Ports}}' 2>&1)"
DOCKER_PS="$(docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1)"
echo "$COMPOSE_PS"
for svc in backend postgres nginx; do
  CID="$(docker compose ps -q "$svc" 2>/dev/null)"
  if [ -z "$CID" ]; then bad "$svc запущен" "контейнер не найден"; continue; fi
  ST="$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$CID")"
  check "$([[ "$ST" == running/healthy || "$ST" == running ]] && echo 0 || echo 1)" "$svc: running/healthy" "$ST"
done
RESTARTING="$(docker inspect -f '{{if .State.Restarting}}{{.Name}} {{end}}' $(docker compose ps -aq) 2>/dev/null | tr -d '\n/' | xargs)"
check "$([ -z "$RESTARTING" ] && echo 0 || echo 1)" "Ни один контейнер не в Restarting" "${RESTARTING:-ни одного}"

echo "=== 2. backend видит БД ==="
DB_PING="$(docker compose exec -T backend python -c "
from sqlalchemy import text
from app.core.db import engine
with engine.connect() as c:
    print('db=', c.execute(text('select current_database()')).scalar(), ' pg=', c.execute(text('show server_version')).scalar(), sep='')
" 2>&1 | tail -n1)"
check "$(grep -q '^db=' <<<"$DB_PING" && echo 0 || echo 1)" "backend → postgres (SQLAlchemy из контейнера)" "$(md "$DB_PING")"
HEALTH="$(curl -s --max-time 10 "$BASE/api/health")"
check "$(grep -q '"status":"ok"' <<<"$HEALTH" && grep -q '"db":"ok"' <<<"$HEALTH" && echo 0 || echo 1)" "GET /api/health через nginx" "\`$HEALTH\`"

echo "=== 3. Услуги ==="
SERVICES="$(curl -s --max-time 10 "$BASE/api/admin-settings")"
N_SVC="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' <<<"$SERVICES" 2>/dev/null || echo 0)"
SVC_NAMES="$(python3 -c 'import json,sys; print(", ".join(f"{s["services"]} ({s["budget_range"]})" for s in json.load(sys.stdin)))' <<<"$SERVICES" 2>/dev/null)"
check "$([ "$N_SVC" -ge 3 ] 2>/dev/null && echo 0 || echo 1)" "GET /api/admin-settings → ≥3 услуги" "$N_SVC шт.: $(md "$SVC_NAMES")"
C_SLASH=$(code "$BASE/api/admin-settings/")
check "$([ "$C_SLASH" = 200 ] && echo 0 || echo 1)" "GET /api/admin-settings/ (со слэшем) без 307" "HTTP $C_SLASH"

echo "=== 4. Статика: index.html, CSS, JS ==="
INDEX="$(curl -s --max-time 10 "$BASE/")"
C_INDEX=$(code "$BASE/")
# Минифицированный HTML может быть без кавычек: href=/assets/main.css — кавычки необязательны
asset() { grep -oE "$1=\"?/assets/[^\" >]+\.$2" | head -n1 | sed -E "s/^$1=\"?//"; }
CSS_PATH="$(asset href css <<<"$INDEX")"
JS_PATH="$(asset src js <<<"$INDEX")"
check "$([ "$C_INDEX" = 200 ] && echo 0 || echo 1)" "GET / (index.html)" "HTTP $C_INDEX"
CSS_HDR="$(curl -s -o /dev/null -D - --max-time 10 "$BASE$CSS_PATH")"
CSS_CODE="$(head -n1 <<<"$CSS_HDR" | awk '{print $2}')"
CSS_TYPE="$(grep -i '^content-type:' <<<"$CSS_HDR" | cut -d' ' -f2- | tr -d '\r')"
check "$([ -n "$CSS_PATH" ] && [ "$CSS_CODE" = 200 ] && grep -qi 'text/css' <<<"$CSS_TYPE" && echo 0 || echo 1)" "CSS ${CSS_PATH:-не найден в index.html}" "HTTP ${CSS_CODE:-—}, Content-Type: ${CSS_TYPE:-—}"
JS_CODE=$(code "$BASE$JS_PATH")
check "$([ -n "$JS_PATH" ] && [ "$JS_CODE" = 200 ] && echo 0 || echo 1)" "JS ${JS_PATH:-не найден в index.html}" "HTTP $JS_CODE"
ADMIN_HTML="$(curl -s --max-time 10 "$BASE/admin/")"
ADMIN_CSS="$(asset href css <<<"$ADMIN_HTML")"
C_ADMIN_CSS=$(code "$BASE$ADMIN_CSS")
check "$([ -n "$ADMIN_CSS" ] && [ "$C_ADMIN_CSS" = 200 ] && echo 0 || echo 1)" "/admin подключает CSS по абсолютному пути" "${ADMIN_CSS:-нет} → HTTP $C_ADMIN_CSS"
C_MISSING=$(code "$BASE/assets/nope.css")
check "$([ "$C_MISSING" = 404 ] && echo 0 || echo 1)" "Несуществующий CSS → 404, а не index.html" "HTTP $C_MISSING"

echo "=== 5. POST без 307/405 ==="
SVC_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])' <<<"$SERVICES" 2>/dev/null || echo 1)"
payload() {
  printf '{"application":{"last_name":"Проверкин","first_name":"%s","phone":"+7 900 000-00-00","service_id":%s,"role":"сотрудник","budget":"50000","comment":"check.sh"},"metrics":{"time_on_page_sec":5,"utm":{"utm_source":"check"}}}' "$1" "$SVC_ID"
}
for path in /api/applications /api/applications/; do
  RES="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST -H 'Content-Type: application/json' --data "$(payload "Слэш${path: -1}")" "$BASE$path")"
  check "$([ "$RES" = 201 ] && echo 0 || echo 1)" "POST $path" "HTTP $RES (ожидается 201, не 307/405)"
done

echo "=== 6. Изоляция backend ==="
BACKEND_PORTS="$(docker port backend 2>/dev/null)"
check "$([ -z "$BACKEND_PORTS" ] && echo 0 || echo 1)" "Контейнер backend не публикует порты" "${BACKEND_PORTS:-docker port backend: пусто}"
BACKEND_NETS="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' backend 2>/dev/null)"
check "$(grep -q '_public' <<<"$BACKEND_NETS" && echo 1 || echo 0)" "backend только в сети internal" "сети: $BACKEND_NETS"
OWNER_8000="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E "(0\.0\.0\.0|::|127\.0\.0\.1):${PORT_INT}->" | awk '{print $1}' | xargs)"
if [ -n "$OWNER_8000" ] && ! grep -qw backend <<<"$OWNER_8000"; then
  NOTE="localhost:${PORT_INT} занят сторонним контейнером ($OWNER_8000) — к стеку не относится; backend стека порт не публикует"
elif (exec 3<>/dev/tcp/127.0.0.1/"$PORT_INT") 2>/dev/null; then
  NOTE="на localhost:${PORT_INT} слушает сторонний процесс (не Docker); backend стека порт не публикует"
else
  NOTE="TCP-подключение к localhost:${PORT_INT} отклонено"
fi
check "$([ -z "$BACKEND_PORTS" ] && echo 0 || echo 1)" "Backend стека недоступен с хоста напрямую" "$NOTE"
NET_TEST="$(docker run --rm --network "${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}_public" alpine:3 sh -c "nc -z -w 3 backend $PORT_INT && echo OPEN || echo CLOSED" 2>/dev/null)"
check "$([ "$NET_TEST" = CLOSED ] && echo 0 || echo 1)" "Из сети public backend недоступен" "nc backend:$PORT_INT → ${NET_TEST:-нет ответа}"

echo "=== 7. Swagger ==="
C_DOCS=$(code "$BASE/docs"); C_OPENAPI=$(code "$BASE/openapi.json")
if [ "${DOCS_ENABLED:-false}" = true ]; then
  check "$([ "$C_DOCS" = 200 ] && [ "$C_OPENAPI" = 200 ] && echo 0 || echo 1)" "DOCS_ENABLED=true: /docs и /openapi.json" "HTTP $C_DOCS / $C_OPENAPI"
else
  check "$([ "$C_DOCS" = 404 ] && [ "$C_OPENAPI" = 404 ] && echo 0 || echo 1)" "DOCS_ENABLED=false: /docs закрыт" "HTTP $C_DOCS / $C_OPENAPI (ожидается 404)"
fi

echo "=== 8. Данные в БД ==="
PSQL=(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB")
N_APP="$("${PSQL[@]}" -tAc 'SELECT count(*) FROM applications' 2>&1 | tr -d '[:space:]')"
N_MET="$("${PSQL[@]}" -tAc 'SELECT count(*) FROM behavior_metrics' 2>&1 | tr -d '[:space:]')"
check "$([[ "$N_APP" =~ ^[0-9]+$ ]] && [ "$N_APP" -gt 0 ] && echo 0 || echo 1)" "SELECT count(*) FROM applications" "$N_APP"
check "$([ "$N_APP" = "$N_MET" ] && echo 0 || echo 1)" "applications = behavior_metrics (связь 1:1)" "$N_APP = $N_MET"
LAST3="$("${PSQL[@]}" -c "SELECT a.id, to_char(a.created_at AT TIME ZONE 'Europe/Moscow','DD.MM HH24:MI') AS created, a.last_name||' '||a.first_name AS fio, s.services AS service, a.budget, a.role, m.time_on_page_sec AS sec, jsonb_array_length(m.clicks) AS clicks, m.utm->>'utm_source' AS utm FROM applications a LEFT JOIN admin_settings s ON s.id=a.service_id LEFT JOIN behavior_metrics m ON m.application_id=a.id ORDER BY a.id DESC LIMIT 3" 2>&1)"
echo "$LAST3"

echo "=== 9. Логи backend ==="
LOGS="$(docker logs --tail 20 backend 2>&1)"
check "$(grep -q 'Traceback' <<<"$LOGS" && echo 1 || echo 0)" "Последние 20 строк docker logs backend без Traceback" "$(grep -c . <<<"$LOGS") строк проверено"

# ---------- Отчёт ----------
TOTAL=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then SUMMARY="✅ Все проверки пройдены: $PASS из $TOTAL"; else SUMMARY="❌ Провалено проверок: $FAIL из $TOTAL"; fi
{
  echo "# Отчёт проверки стека Autello — часть 2"
  echo
  echo "- Дата: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "- Режим: $( is_mock && echo 'эмуляция (MOCK_MODE=true), локальный Docker' || echo "боевой, VPS $VPS_HOST")"
  echo "- DOCS_ENABLED: ${DOCS_ENABLED:-false}"
  echo "- Docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null), $(docker compose version --short 2>/dev/null | sed 's/^/compose /')"
  echo
  echo "## Итог"
  echo
  echo "**$SUMMARY**"
  echo
  echo "## Проверки"
  echo
  echo "| | Проверка | Результат |"
  echo "|---|---|---|"
  printf '%s\n' "${ROWS[@]}"
  echo
  echo "## docker compose ps"
  echo; echo '```'; echo "$COMPOSE_PS"; echo '```'
  echo
  echo "## docker ps"
  echo; echo '```'; echo "$DOCKER_PS"; echo '```'
  echo
  echo "## Последние 3 заявки (всего: $N_APP, метрик: $N_MET)"
  echo; echo '```'; echo "$LAST3"; echo '```'
  echo
  echo "## docker logs --tail 20 backend"
  echo; echo '```'; echo "$LOGS"; echo '```'
  echo
  echo "## Адреса"
  echo
  echo "- Сайт: $BASE/"
  echo "- Админка: $BASE/admin"
  echo "- Swagger: $BASE/docs $([ "${DOCS_ENABLED:-false}" = true ] && echo '(открыт временно)' || echo '(закрыт)')"
  echo "- pgAdmin: http://localhost:${PGADMIN_PORT} (логин: \`$PGADMIN_DEFAULT_EMAIL\`)"
  echo "- Registry UI: http://localhost:${REGISTRY_UI_PORT}"
  echo "- Скриншоты e2e: reports/screens/"
} > "$REPORT"

echo
echo "$SUMMARY"
echo "Отчёт: $REPORT"
[ "$FAIL" -eq 0 ]
