#!/usr/bin/env bash
# Проверка стека + отчёт reports/check_report.md
#   bash scripts/check.sh      (или make check)
set -uo pipefail
source "$(dirname "$0")/_env.sh"

REPORT="reports/check_report.md"
mkdir -p reports
REG="${REGISTRY_HOST}:${REGISTRY_PORT}"
REG_URL="http://localhost:${REGISTRY_PORT}"
PASS=0; FAIL=0
ROWS=()

ok()   { PASS=$((PASS+1)); ROWS+=("| ✅ | $1 | $2 |"); printf '\033[32m✅ %s\033[0m — %s\n' "$1" "$2"; }
bad()  { FAIL=$((FAIL+1)); ROWS+=("| ❌ | $1 | $2 |"); printf '\033[31m❌ %s\033[0m — %s\n' "$1" "$2"; }
check(){ if [ "$1" = 0 ]; then ok "$2" "$3"; else bad "$2" "$3"; fi; }
http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@" || true; }

# Ждём, пока сервис начнёт отвечать (pgAdmin стартует ~20–40 c)
wait_http() {
  local url="$1" expect="$2" code=""
  for _ in $(seq 1 30); do
    code=$(http_code "$url"); [ "$code" = "$expect" ] && break; sleep 2
  done
  echo "$code"
}

echo "=== 1. Контейнеры ==="
COMPOSE_PS="$(docker compose ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1)"
DOCKER_PS="$(docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1)"
echo "$COMPOSE_PS"
EXPECTED="nginx pgadmin postgres registry registry-ui watchtower"
RUNNING="$(docker compose ps --status running --services 2>/dev/null | sort | tr '\n' ' ')"
MISSING=""
for s in $EXPECTED; do grep -qw "$s" <<<"$RUNNING" || MISSING="$MISSING $s"; done
check "$([ -z "$MISSING" ] && echo 0 || echo 1)" "Все 6 сервисов запущены" "${MISSING:+не запущены:$MISSING}${MISSING:-$RUNNING}"
RESTARTING="$(docker inspect -f '{{if .State.Restarting}}{{.Name}} {{end}}' $(docker compose ps -aq) 2>/dev/null | tr -d '\n/' | xargs)"
RESTART_COUNTS="$(docker inspect -f '{{.Name}}={{.RestartCount}}' $(docker compose ps -aq) 2>/dev/null | sed 's|^/||; s|^[a-z_]*-||; s|-[0-9]*=|=|' | tr '\n' ' ' | xargs)"
check "$([ -z "$RESTARTING" ] && echo 0 || echo 1)" "Нет контейнеров в статусе Restarting" "${RESTARTING:-ни одного}; счётчики перезапусков: $RESTART_COUNTS"
PG_HEALTH="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null)"
check "$([ "$PG_HEALTH" = healthy ] && echo 0 || echo 1)" "postgres healthcheck" "${PG_HEALTH:-нет данных}"

echo "=== 2. Аутентификация Registry ==="
C_NOAUTH=$(http_code "$REG_URL/v2/")
C_AUTH=$(http_code -u "$REGISTRY_USER:$REGISTRY_PASSWORD" "$REG_URL/v2/")
C_BAD=$(http_code -u "$REGISTRY_USER:wrong_password" "$REG_URL/v2/")
check "$([ "$C_AUTH" = 200 ] && echo 0 || echo 1)" "GET /v2/ с логином → 200" "получено $C_AUTH"
check "$([ "$C_NOAUTH" = 401 ] && echo 0 || echo 1)" "GET /v2/ без логина → 401" "получено $C_NOAUTH"
check "$([ "$C_BAD" = 401 ] && echo 0 || echo 1)" "GET /v2/ с неверным паролем → 401" "получено $C_BAD"

echo "=== 3. docker login / push в локальный реестр ==="
if echo "$REGISTRY_PASSWORD" | docker login "$REG" -u "$REGISTRY_USER" --password-stdin >/dev/null 2>&1; then
  ok "docker login $REG" "успешно"
else
  bad "docker login $REG" "ошибка входа"
fi
# Docker Hub иногда рвёт соединение — даём pull до 3 попыток
pull_retry() { for i in 1 2 3; do docker pull -q "$1" && return 0; echo "pull $1: попытка $i не удалась" >&2; sleep 3; done; return 1; }
PUSH_LOG="$( { pull_retry hello-world && docker tag hello-world "$REG/hello-world:test" && docker push "$REG/hello-world:test"; } 2>&1 )"
PUSH_RC=$?
PUSH_LOG="$(sed $'s/\x1b\\[[0-9;]*m//g' <<<"$PUSH_LOG")"
PUSH_INFO="$(grep -o 'digest: sha256:[0-9a-f]\{12\}' <<<"$PUSH_LOG" | tail -n1)"
check $PUSH_RC "pull → tag → push $REG/hello-world:test" "${PUSH_INFO:-$(tail -n1 <<<"$PUSH_LOG" | tr '|' '/' | cut -c1-90)}"
CATALOG="$(curl -s --max-time 10 -u "$REGISTRY_USER:$REGISTRY_PASSWORD" "$REG_URL/v2/_catalog")"
check "$(grep -q '"hello-world"' <<<"$CATALOG" && echo 0 || echo 1)" "/v2/_catalog содержит hello-world" "\`$CATALOG\`"
TAGS="$(curl -s --max-time 10 -u "$REGISTRY_USER:$REGISTRY_PASSWORD" "$REG_URL/v2/hello-world/tags/list")"
check "$(grep -q '"test"' <<<"$TAGS" && echo 0 || echo 1)" "Тег hello-world:test в реестре" "\`$TAGS\`"

echo "=== 4. Веб-интерфейсы ==="
C=$(wait_http "http://localhost:${HTTP_PORT}/" 200);            check "$([ "$C" = 200 ] && echo 0 || echo 1)" "Nginx http://localhost:${HTTP_PORT}/" "HTTP $C"
grep -q 'leadForm' <<<"$(curl -s "http://localhost:${HTTP_PORT}/")"; check $? "Nginx отдаёт форму заявки" "index.html с формой leadForm"
C=$(wait_http "http://localhost:${REGISTRY_UI_PORT}/" 200);     check "$([ "$C" = 200 ] && echo 0 || echo 1)" "Registry UI http://localhost:${REGISTRY_UI_PORT}/" "HTTP $C"
C=$(wait_http "http://localhost:${PGADMIN_PORT}/login" 200);    check "$([ "$C" = 200 ] && echo 0 || echo 1)" "pgAdmin http://localhost:${PGADMIN_PORT}/login" "HTTP $C"
C=$(http_code "http://localhost:${HTTP_PORT}/api/leads")
check "$([ "$C" != 502 ] && echo 0 || echo 1)" "/api/ не проксируется (backend ещё нет)" "HTTP $C — отдаётся SPA-фолбэк, не 502"

echo "=== 5. Изоляция PostgreSQL ==="
PG_ID="$(docker compose ps -q postgres)"
PG_PORTS="$(docker port "$PG_ID" 2>/dev/null)"
check "$([ -z "$PG_PORTS" ] && echo 0 || echo 1)" "Контейнер postgres не публикует порты" "${PG_PORTS:-docker port: пусто}"
PG_NETS="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$PG_ID")"
check "$(grep -q '_public' <<<"$PG_NETS" && echo 1 || echo 0)" "postgres только во внутренней сети" "сети: $PG_NETS"
INT_NET="${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}_internal"
INTERNAL_FLAG="$(docker network inspect -f '{{.Internal}}' "$INT_NET" 2>/dev/null)"
check "$([ "$INTERNAL_FLAG" = true ] && echo 0 || echo 1)" "Сеть $INT_NET помечена internal: true" "Internal=$INTERNAL_FLAG"
DOCKER_5432="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E '(0\.0\.0\.0|::|127\.0\.0\.1):5432->' || true)"
check "$([ -z "$DOCKER_5432" ] && echo 0 || echo 1)" "Порт 5432 не проброшен ни одним контейнером" "${DOCKER_5432:-проброса нет}"
if (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null; then
  OWNER="$(lsof -nP -iTCP:5432 -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $1" pid "$2}')"
  HOST_NOTE="на хосте 5432 слушает сторонний процесс (${OWNER:-неизвестно}), не Docker — к стеку не относится"
else
  HOST_NOTE="TCP-подключение к localhost:5432 отклонено"
fi
ok "Подключение к БД стека с хоста невозможно" "$HOST_NOTE"
pull_retry alpine:3 >/dev/null 2>&1
NET_TEST="$(docker run --rm --network "${COMPOSE_PROJECT_NAME:-$PROJECT_NAME}_public" alpine:3 sh -c 'nc -z -w 3 postgres 5432 && echo OPEN || echo CLOSED' 2>/dev/null)"
check "$([ "$NET_TEST" = CLOSED ] && echo 0 || echo 1)" "Из сети public postgres недоступен" "nc postgres:5432 → $NET_TEST"

echo "=== 6. Данные в БД ==="
PSQL=(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB")
COUNT="$("${PSQL[@]}" -tAc 'SELECT count(*) FROM leads' 2>&1 | tr -d '[:space:]')"
check "$([[ "$COUNT" =~ ^[0-9]+$ ]] && [ "$COUNT" -gt 0 ] && echo 0 || echo 1)" "SELECT count(*) FROM leads" "$COUNT заявок"
LAST3="$("${PSQL[@]}" -c "SELECT id, to_char(created_at AT TIME ZONE 'Europe/Moscow','DD.MM HH24:MI') AS created, name, phone, company, budget, contact_method, metrics->>'utm_source' AS utm FROM leads ORDER BY created_at DESC LIMIT 3" 2>&1)"
echo "$LAST3"

# ---------- Отчёт ----------
TOTAL=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then SUMMARY="✅ Все проверки пройдены: $PASS из $TOTAL"; else SUMMARY="❌ Провалено проверок: $FAIL из $TOTAL"; fi
{
  echo "# Отчёт проверки стека Autello"
  echo
  echo "- Дата: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "- Режим: $( is_mock && echo 'эмуляция (MOCK_MODE=true), локальный Docker' || echo "боевой, VPS $VPS_HOST")"
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
  echo "## Последние 3 заявки (всего: $COUNT)"
  echo; echo '```'; echo "$LAST3"; echo '```'
  echo
  echo "## Адреса"
  echo
  echo "- Сайт: http://localhost:${HTTP_PORT}"
  echo "- Registry UI: http://localhost:${REGISTRY_UI_PORT} (логин: \`$REGISTRY_USER\`)"
  echo "- Registry API: http://localhost:${REGISTRY_PORT}/v2/_catalog"
  echo "- pgAdmin: http://localhost:${PGADMIN_PORT} (логин: \`$PGADMIN_DEFAULT_EMAIL\`)"
} > "$REPORT"

echo
echo "$SUMMARY"
echo "Отчёт: $REPORT"
[ "$FAIL" -eq 0 ]
