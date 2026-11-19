#!/usr/bin/env bash
# Создаёт или обновляет пользователя локального Docker Registry.
#   ./create-user.sh <user> <password>
# Пишет в registry/auth/htpasswd (bcrypt), используя htpasswd из образа httpd:2,
# поэтому на хосте ничего ставить не нужно.
# Гарантии: один файл htpasswd (всегда рядом со скриптом), одна строка на пользователя.
set -euo pipefail

if [ $# -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
  echo "Использование: $0 <user> <password>" >&2
  exit 1
fi
USER_NAME="$1"
USER_PASS="$2"

if [[ ! "$USER_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Недопустимое имя пользователя: $USER_NAME (разрешены A-Z a-z 0-9 . _ -)" >&2
  exit 1
fi

# Всегда работаем относительно папки скрипта — не плодим htpasswd по разным каталогам
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTH_DIR="$SCRIPT_DIR/auth"
HTPASSWD="$AUTH_DIR/htpasswd"
mkdir -p "$AUTH_DIR"
touch "$HTPASSWD"

# Генерируем строку user:hash (-B bcrypt, -b пароль из аргумента, -n в stdout)
NEW_LINE="$(docker run --rm httpd:2 htpasswd -Bbn "$USER_NAME" "$USER_PASS" | tr -d '\r' | sed '/^$/d')"
if [ -z "$NEW_LINE" ]; then
  echo "Не удалось сгенерировать хэш (docker запущен?)" >&2
  exit 1
fi

# Атомарная перезапись: убираем старую запись пользователя и добавляем новую
TMP="$(mktemp "$AUTH_DIR/htpasswd.XXXXXX.tmp")"
trap 'rm -f "$TMP"' EXIT
if grep -q "^${USER_NAME}:" "$HTPASSWD"; then ACTION="обновлён"; else ACTION="создан"; fi
grep -v "^${USER_NAME}:" "$HTPASSWD" > "$TMP" || true
echo "$NEW_LINE" >> "$TMP"
chmod 644 "$TMP"   # файл читает процесс внутри контейнера registry
mv "$TMP" "$HTPASSWD"
trap - EXIT

echo "Пользователь реестра '$USER_NAME' $ACTION в $HTPASSWD (всего записей: $(wc -l < "$HTPASSWD" | tr -d ' '))"

# Если реестр уже запущен — перезапускаем, чтобы он перечитал htpasswd
cd "$SCRIPT_DIR/.."
if docker compose ps --status running --services 2>/dev/null | grep -qx registry; then
  docker compose restart registry >/dev/null && echo "Контейнер registry перезапущен"
fi
