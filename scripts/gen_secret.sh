#!/usr/bin/env bash
# Готовит .env для части 3:
#   1) создаёт .env из example.env, если его нет;
#   2) дописывает в .env переменные из example.env, которых там ещё нет (новые для части 3);
#   3) если SECRET_KEY — заглушка, генерирует настоящий: openssl rand -hex 32.
# Существующие значения НЕ трогает. Запуск: make secret
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp example.env .env
  echo "Создан .env из example.env — замените пароли на свои"
fi

added=0
while IFS= read -r line; do
  [[ "$line" =~ ^[A-Z_][A-Z0-9_]*= ]] || continue
  key="${line%%=*}"
  if ! grep -qE "^${key}=" .env; then
    [ "$added" = 0 ] && printf '\n# === Добавлено make secret из example.env (часть 3) ===\n' >> .env
    echo "$line" >> .env
    added=$((added+1))
    echo "  + $key"
  fi
done < example.env
[ "$added" -gt 0 ] && echo "Добавлено переменных: $added" || echo "Все переменные example.env уже есть в .env"

current="$(grep -E '^SECRET_KEY=' .env | tail -n1 | cut -d= -f2-)"
if [ -z "$current" ] || [[ "$current" == replace_with* ]] || [ "${#current}" -lt 32 ]; then
  if command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -hex 32)"
  else
    secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  fi
  # sed -i по-разному работает в GNU и BSD (macOS) — переписываем файл через временный
  tmp="$(mktemp)"
  awk -v s="$secret" 'BEGIN{done=0} /^SECRET_KEY=/{ if(!done){print "SECRET_KEY=" s; done=1}; next } {print}' .env > "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
  echo "SECRET_KEY сгенерирован (openssl rand -hex 32) и записан в .env"
else
  echo "SECRET_KEY уже задан — не меняю (иначе разлогинятся все админы)"
fi
