#!/usr/bin/env bash
# Проверка стека (часть 3) → reports/check_report.md
#   bash scripts/check.sh      (или make check)
#
# Блок «функции» работает в любом режиме (dev и secure): вход, CRUD, метрики, приоритизация, pytest.
# Блок «безопасность» — только в защищённом режиме (make secure): https, 301, 403, закрытые порты.
set -uo pipefail
source "$(dirname "$0")/_env.sh"

REPORT="reports/check_report.md"
mkdir -p reports
PASS=0; FAIL=0; SKIP=0
ROWS=()
SECTION=""

ok()   { PASS=$((PASS+1)); ROWS+=("| ✅ | $SECTION | $1 | $2 |"); printf '\033[32m✅ %s\033[0m — %s\n' "$1" "$2"; }
bad()  { FAIL=$((FAIL+1)); ROWS+=("| ❌ | $SECTION | $1 | $2 |"); printf '\033[31m❌ %s\033[0m — %s\n' "$1" "$2"; }
skip() { SKIP=$((SKIP+1)); ROWS+=("| ⏭ | $SECTION | $1 | $2 |"); printf '\033[33m⏭ %s\033[0m — %s\n' "$1" "$2"; }
check(){ if [ "$1" = 0 ]; then ok "$2" "$3"; else bad "$2" "$3"; fi; }
# Безопасно для ячейки markdown-таблицы; режем по символам, а не байтам (кириллица в UTF-8)
md()   { python3 -c 'import sys; s=sys.argv[1].replace("|","/").replace("\n"," "); print(s[:200] + ("…" if len(s) > 200 else ""))' "$1"; }
J()    { python3 "$PROJECT_ROOT/scripts/_check_json.py" "$1"; }   # разбор JSON: scripts/_check_json.py
section() { SECTION="$1"; echo; echo "=== $1 ==="; }

# ---------- Режим и адреса ----------
NGINX_MODE="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' nginx 2>/dev/null | sed -n 's/^NGINX_MODE=//p')"
NGINX_MODE="${NGINX_MODE:-неизвестен}"
HTTP_BASE="http://localhost$([ "${HTTP_PORT:-80}" = 80 ] || echo ":$HTTP_PORT")"
HTTPS_BASE="https://localhost$([ "${HTTPS_PORT:-443}" = 443 ] || echo ":$HTTPS_PORT")"
BASE="$HTTPS_BASE"
# -k: самоподписанный сертификат (make certs). На VPS с Let's Encrypt — тоже работает
CURL=(curl -sk --max-time 10)
code() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$@" || true; }
echo "Режим nginx: $NGINX_MODE · API: $BASE"

# =====================================================================
section "Контейнеры"
COMPOSE_PS="$(docker compose --profile admin-tools ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Ports}}' 2>&1)"
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

# =====================================================================
section "Авторизация (п.1)"
AUTH_CHECK="$("${CURL[@]}" "$BASE/api/auth/check")"
check "$(grep -q '"has_admins":true' <<<"$AUTH_CHECK" && echo 0 || echo 1)" "GET /api/auth/check" "\`$AUTH_CHECK\` (админ зарегистрирован → кнопки «Зарегистрироваться» нет)"
LOGIN="$("${CURL[@]}" -X POST "$BASE/api/auth/login" --data-urlencode "username=${DEMO_ADMIN_USER:-admin}" --data-urlencode "password=${DEMO_ADMIN_PASSWORD:-change_me_demo}")"
TOKEN="$(J token <<<"$LOGIN")"
check "$([ -n "$TOKEN" ] && echo 0 || echo 1)" "POST /api/auth/login (form-data) → JWT" "$([ -n "$TOKEN" ] && echo "token_type=bearer, длина ${#TOKEN}" || md "$LOGIN")"
AUTH=(-H "Authorization: Bearer $TOKEN")
ME_CODE="$(code "${AUTH[@]}" "$BASE/api/auth/me")"
check "$([ "$ME_CODE" = 200 ] && echo 0 || echo 1)" "GET /api/auth/me с токеном" "HTTP $ME_CODE"
REG_CODE="$(code -X POST -H 'Content-Type: application/json' -d '{"username":"intruder","password":"intruder_pass"}' "$BASE/api/auth/register")"
check "$([ "$REG_CODE" = 403 ] && echo 0 || echo 1)" "Повторная регистрация закрыта" "POST /api/auth/register → HTTP $REG_CODE (ожидается 403)"
DEL_NOAUTH="$(code -X DELETE "$BASE/api/admin-settings/1")"
check "$([ "$DEL_NOAUTH" = 401 ] && echo 0 || echo 1)" "DELETE /api/admin-settings/1 без токена" "HTTP $DEL_NOAUTH (ожидается 401)"
APPS_NOAUTH="$(code "$BASE/api/applications/ranked")"
check "$([ "$APPS_NOAUTH" = 401 ] && echo 0 || echo 1)" "GET /api/applications/ranked без токена" "HTTP $APPS_NOAUTH (ожидается 401)"

# =====================================================================
section "Услуги (п.2)"
SERVICES="$("${CURL[@]}" "$BASE/api/admin-settings?only_active=true")"
N_SVC="$(J count <<<"$SERVICES")"
check "$([ "${N_SVC:--1}" -ge 5 ] 2>/dev/null && echo 0 || echo 1)" "GET /api/admin-settings — массив, ≥5 активных услуг" "$(md "$(J services <<<"$SERVICES")")"
NAME="check.sh услуга $(date +%H%M%S)"
CREATED="$("${CURL[@]}" -X POST "${AUTH[@]}" -H 'Content-Type: application/json' -d "{\"services\":\"$NAME\",\"budget_min\":1000,\"budget_max\":5000}" "$BASE/api/admin-settings")"
SID="$(J id <<<"$CREATED")"
PUT_CODE="$(code -X PUT "${AUTH[@]}" -H 'Content-Type: application/json' -d '{"budget_max":7000}' "$BASE/api/admin-settings/$SID")"
IN_LIST="$("${CURL[@]}" "$BASE/api/admin-settings?only_active=true" | python3 -c "import json,sys; print(any(s['id']==${SID:-0} and s['budget_max']==7000 for s in json.load(sys.stdin)))")"
DEL_CODE="$(code -X DELETE "${AUTH[@]}" "$BASE/api/admin-settings/$SID")"
GONE="$("${CURL[@]}" "$BASE/api/admin-settings?only_active=true" | python3 -c "import json,sys; print(all(s['id']!=${SID:-0} for s in json.load(sys.stdin)))")"
check "$([ -n "$SID" ] && [ "$PUT_CODE" = 200 ] && [ "$IN_LIST" = True ] && [ "$DEL_CODE" = 204 ] && [ "$GONE" = True ] && echo 0 || echo 1)" \
  "CRUD-цикл услуги с токеном" "POST → id ${SID:-—}, PUT → $PUT_CODE, в списке: $IN_LIST, DELETE → $DEL_CODE, исчезла из списка главной: $GONE"
C_SLASH="$(code "$BASE/api/admin-settings/")"
check "$([ "$C_SLASH" = 200 ] && echo 0 || echo 1)" "GET /api/admin-settings/ (со слэшем) без 307" "HTTP $C_SLASH"

# =====================================================================
section "Метрики (п.3)"
PSQL=(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA)
VA="reports/visitor_activity.json"
if [ -f "$VA" ]; then
  VA_LINE="$(python3 -c "
import json; d=json.load(open('$VA')); r=d['metrics_rows']; v=d['visits'][0]
ok = r['during_12s'] > r['before'] and r['after'] >= r['before'] + 3 and v['time_on_page'] >= d['visit_seconds'] - 10
print('OK' if ok else 'FAIL', f\"строк до: {r['before']}, через 12 с: {r['during_12s']}, после: {r['after']}; долгий визит {v['time_on_page']} с, точек курсора {v['cursor_points']}, возвратов {v['return_frequency']} ({d['finished_at'][:16]})\")")"
  check "$([[ "$VA_LINE" == OK* ]] && echo 0 || echo 1)" "count(*) behavior_metrics растёт во время visitor_activity (e2e)" "${VA_LINE#* }"
else
  bad "count(*) behavior_metrics растёт во время visitor_activity (e2e)" "нет $VA — запустите make e2e"
fi
N0="$("${PSQL[@]}" -c 'SELECT count(*) FROM behavior_metrics' | tr -d '[:space:]')"
SESS="check-$(date +%s)"
for t in 1 2 3; do
  "${CURL[@]}" -o /dev/null -X POST -H 'Content-Type: application/json' \
    -d "{\"application_id\":0,\"time_on_page\":$t,\"buttons_clicked\":\"{\\\"submit\\\":$t}\",\"cursor_positions\":\"[{\\\"x\\\":0.4,\\\"y\\\":0.3}]\",\"return_frequency\":0,\"session_id\":\"$SESS\"}" \
    "$BASE/api/behavior-metrics"
  sleep 1
done
N1="$("${PSQL[@]}" -c 'SELECT count(*) FROM behavior_metrics' | tr -d '[:space:]')"
ROW="$("${PSQL[@]}" -c "SELECT time_on_page FROM behavior_metrics WHERE session_id='$SESS'" | tr -d '[:space:]')"
check "$([ "$((N1-N0))" = 1 ] && [ "$ROW" = 3 ] && echo 0 || echo 1)" "3 снимка одного визита (формат урока) → 1 строка, upsert" "строк было $N0, стало $N1; time_on_page=$ROW"
LESSON="$(code -X POST -H 'Content-Type: application/json' -d '{"application_id":0,"time_on_page":0,"buttons_clicked":"string","cursor_positions":"string","return_frequency":0}' "$BASE/api/behavior-metrics/")"
LESSON2="$(code -X POST -H 'Content-Type: application/json' -d '{"application_id":0,"time_on_page":0,"buttons_clicked":"string","cursor_positions":"string","return_frequency":0}' "$BASE/api/behavior-metrics/")"
check "$([ "$LESSON" = 201 ] && [ "$LESSON2" = 201 ] && echo 0 || echo 1)" "Пример из Swagger дважды подряд (application_id=0)" "HTTP $LESSON, $LESSON2 — ошибки «already exists» нет"
STATS="$("${CURL[@]}" "${AUTH[@]}" "$BASE/api/behavior-metrics/stats")"
STATS_LINE="$(J stats <<<"$STATS")"
check "$([[ "$STATS_LINE" == OK* ]] && echo 0 || echo 1)" "GET /api/behavior-metrics/stats: 3 периода + heatmap" "$(md "${STATS_LINE#* }")"

# =====================================================================
section "Приоритизация (п.4)"
RANKED="$("${CURL[@]}" "${AUTH[@]}" "$BASE/api/applications/ranked")"
DIST="$(J dist <<<"$RANKED")"
check "$([ "$DIST" = 4/3/3 ] && echo 0 || echo 1)" "/ranked: 10 тестовых заявок → 🔥/🌤/❄️" "${DIST:-нет данных} (ожидается 4/3/3; make test-sql)"
SORTED="$(J sorted <<<"$RANKED")"
TOP="$(J top4 <<<"$RANKED")"
check "$([ "$SORTED" = True ] && echo 0 || echo 1)" "/ranked отсортирован по score" "первые 4: $(md "$TOP")"
SUMMARY="$("${CURL[@]}" "${AUTH[@]}" "$BASE/api/applications/summary")"
SUM_LINE="$(J summary <<<"$SUMMARY")"
check "$([[ "$SUM_LINE" == OK* ]] && echo 0 || echo 1)" "GET /api/applications/summary" "$(md "${SUM_LINE#* }")"
APP_ID="$(J first_id <<<"$RANKED")"
DETAIL="$(code "${AUTH[@]}" "$BASE/api/applications/$APP_ID")"
check "$([ "$DETAIL" = 200 ] && echo 0 || echo 1)" "GET /api/applications/{id} (заявка + оценка)" "id $APP_ID → HTTP $DETAIL"
PYTEST="$(docker compose run --rm --no-deps -T backend python -m pytest -q -p no:cacheprovider tests 2>&1 | tail -n 3)"
check "$(grep -qE '[0-9]+ passed' <<<"$PYTEST" && ! grep -qE 'failed|error' <<<"$PYTEST" && echo 0 || echo 1)" "pytest tests/test_lead_scoring.py" "$(md "$(tail -n1 <<<"$PYTEST")")"

# =====================================================================
section "Фронт и прокси"
INDEX="$("${CURL[@]}" "$BASE/")"
asset() { grep -oE "$1=\"?/assets/[^\" >]+\.$2" | head -n1 | sed -E "s/^$1=\"?//"; }
CSS_PATH="$(asset href css <<<"$INDEX")"
CSS_TYPE="$("${CURL[@]}" -o /dev/null -w '%{http_code} %{content_type}' "$BASE$CSS_PATH")"
check "$([ -n "$CSS_PATH" ] && grep -q '^200 text/css' <<<"$CSS_TYPE" && echo 0 || echo 1)" "CSS главной" "${CSS_PATH:-не найден} → $CSS_TYPE"
ADMIN_JS="$(asset src js <<<"$("${CURL[@]}" "$BASE/admin/")")"
check "$([ "$(code "$BASE$ADMIN_JS")" = 200 ] && echo 0 || echo 1)" "/admin подключает JS по абсолютному пути" "${ADMIN_JS:-нет}"
SVC_ID="$(J first_id <<<"$SERVICES")"
for path in /api/applications /api/applications/; do
  RES="$(code -X POST -H 'Content-Type: application/json' --data "{\"application\":{\"last_name\":\"Проверкин\",\"first_name\":\"Чек\",\"phone\":\"+7 900 000-00-00\",\"service_id\":${SVC_ID:-1},\"role\":\"сотрудник\",\"comment\":\"check.sh\"}}" "$BASE$path")"
  check "$([ "$RES" = 201 ] && echo 0 || echo 1)" "POST $path (публичный)" "HTTP $RES (ожидается 201, не 307/405)"
done
DOUBLE="$(code "$BASE/api/api/auth/check")"
check "$([ "$DOUBLE" = 404 ] && [ "$(code "$BASE/api/auth/check")" = 200 ] && echo 0 || echo 1)" "Нет двойного /api/api" "/api/auth/check → 200, /api/api/auth/check → $DOUBLE"

# =====================================================================
section "Безопасность (п.5)"
if [ "$NGINX_MODE" = secure ]; then
  C_HTTPS="$(code "$HTTPS_BASE/")"
  check "$([ "$C_HTTPS" = 200 ] && echo 0 || echo 1)" "curl -k $HTTPS_BASE" "HTTP $C_HTTPS"
  REDIR="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 "$HTTP_BASE/admin")"
  check "$([[ "$REDIR" == "301 https://"* ]] && echo 0 || echo 1)" "curl $HTTP_BASE → 301 на https" "$REDIR"
  for p in "${STUB_BACKEND_PORT:-8000}:backend" "${STUB_POSTGRES_PORT:-5432}:PostgreSQL"; do
    port="${p%%:*}"; what="${p#*:}"
    C="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$port/")"
    check "$([ "$C" = 403 ] && echo 0 || echo 1)" "curl http://localhost:$port → 403" "HTTP $C (заглушка nginx; реальный $what не опубликован)"
  done
  for port in "${PGADMIN_PORT:-5050}" "${REGISTRY_PORT:-5000}" "${REGISTRY_UI_PORT:-8080}"; do
    curl -s -o /dev/null --max-time 5 "http://localhost:$port/"; rc=$?
    OWNER="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E ":${port}->" | awk '{print $1}' | xargs)"
    check "$([ "$rc" = 7 ] && echo 0 || echo 1)" "localhost:$port — соединение отклонено" "curl exit $rc$([ "$rc" = 7 ] && echo ' (Connection refused)')${OWNER:+, порт держит $OWNER}"
  done
  PUBLISHED="$(for c in $(docker compose ps -q); do n="$(docker inspect -f '{{.Name}}' "$c" | tr -d /)"; p="$(docker port "$c" 2>/dev/null | xargs)"; [ -n "$p" ] && echo "$n"; done | sort -u | xargs)"
  check "$([ "$PUBLISHED" = nginx ] && echo 0 || echo 1)" "docker ps: порты опубликованы только у nginx" "с портами: ${PUBLISHED:-никто}"
  C_DOCS="$(code "$HTTPS_BASE/docs")"; C_OPENAPI="$(code "$HTTPS_BASE/openapi.json")"
  check "$([ "$C_DOCS" = 404 ] && [ "$C_OPENAPI" = 404 ] && echo 0 || echo 1)" "/docs и /openapi.json закрыты" "HTTP $C_DOCS / $C_OPENAPI (ожидается 404)"
  BACKEND_NETS="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' backend 2>/dev/null)"
  check "$(grep -q '_public' <<<"$BACKEND_NETS" && echo 1 || echo 0)" "backend только во внутренней сети" "сети: $BACKEND_NETS"
  HDRS="$(curl -skI --max-time 10 "$HTTPS_BASE/")"
  HTTPV="$(curl -sk -o /dev/null -w '%{http_version}' --max-time 10 "$HTTPS_BASE/")"
  check "$(grep -qi '^strict-transport-security: max-age=' <<<"$HDRS" && grep -qi '^x-content-type-options: nosniff' <<<"$HDRS" && echo 0 || echo 1)" "HSTS и security-заголовки" "HTTP/$HTTPV; $(md "$(grep -iE '^(strict-transport|x-frame|x-content)' <<<"$HDRS" | tr -d '\r' | tr '\n' ';')")"
  if curl -sk -o /dev/null --max-time 5 --tls-max 1.1 "$HTTPS_BASE/" 2>/dev/null; then TLS_OLD=принят; else TLS_OLD=отклонён; fi
  check "$([ "$TLS_OLD" = отклонён ] && echo 0 || echo 1)" "TLS 1.0/1.1 отключены (только TLS 1.2+)" "TLS ≤1.1 $TLS_OLD"
else
  for item in "https://localhost = 200" "http://localhost = 301" ":8000 и :5432 = 403" ":5050/:5000/:8080 закрыты" "порты только у nginx" "/docs = 404"; do
    skip "$item" "режим $NGINX_MODE — запустите make secure и make check"
  done
fi

section "Логи (п.6)"
LOGS="$(docker logs --tail 50 backend 2>&1)"
check "$(grep -q 'Traceback' <<<"$LOGS" && echo 1 || echo 0)" "Последние 50 строк docker logs backend без Traceback" "$(grep -c . <<<"$LOGS") строк проверено"

# ---------- Отчёт ----------
TOTAL=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then SUMMARY_LINE="✅ Все проверки пройдены: $PASS из $TOTAL"; else SUMMARY_LINE="❌ Провалено проверок: $FAIL из $TOTAL"; fi
[ "$SKIP" -gt 0 ] && SUMMARY_LINE="$SUMMARY_LINE (пропущено в режиме $NGINX_MODE: $SKIP)"
LAST="$("${PSQL[@]}" -F ' | ' -c "SELECT count(*) AS n, round(avg(time_on_page)), max(time_on_page) FROM behavior_metrics" 2>&1)"
{
  echo "# Отчёт проверки стека Autello — часть 3"
  echo
  echo "- Дата: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "- Режим nginx: **$NGINX_MODE** · $( is_mock && echo 'эмуляция (MOCK_MODE=true), локальный Docker' || echo "боевой, VPS $VPS_HOST")"
  echo "- Адрес API в проверках: $BASE"
  echo "- Порты-заглушки: backend → ${STUB_BACKEND_PORT:-8000}, PostgreSQL → ${STUB_POSTGRES_PORT:-5432}"
  echo "- Docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null), $(docker compose version --short 2>/dev/null | sed 's/^/compose /')"
  echo
  echo "## Итог"
  echo
  echo "**$SUMMARY_LINE**"
  echo
  echo "## Проверки"
  echo
  echo "| | Раздел | Проверка | Результат |"
  echo "|---|---|---|---|"
  printf '%s\n' "${ROWS[@]}"
  echo
  echo "## docker compose ps"
  echo; echo '```'; echo "$COMPOSE_PS"; echo '```'
  echo
  echo "## docker ps (все контейнеры машины)"
  echo; echo '```'; echo "$DOCKER_PS"; echo '```'
  echo
  echo "## behavior_metrics: строк / среднее / максимум, с"
  echo; echo '```'; echo "$LAST"; echo '```'
  echo
  echo "## docker logs --tail 50 backend"
  echo; echo '```'; echo "$LOGS"; echo '```'
  echo
  echo "## Адреса"
  echo
  echo "- Сайт: $HTTPS_BASE/ (в dev также $HTTP_BASE/)"
  echo "- Админка: $HTTPS_BASE/admin"
  echo "- Swagger (dev): http://localhost:${BACKEND_DEV_PORT:-8000}/docs"
  echo "- Скриншоты e2e: reports/screens/"
} > "$REPORT"

echo
echo "$SUMMARY_LINE"
echo "Отчёт: $REPORT"
[ "$FAIL" -eq 0 ]
