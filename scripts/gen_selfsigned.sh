#!/usr/bin/env bash
# Самоподписанный сертификат для локального HTTPS (и для VPS до получения Let's Encrypt).
#   CN=localhost, SAN: localhost, 127.0.0.1, ::1 + VPS_DOMAIN и VPS_HOST из .env (если заданы).
# Кладёт nginx/certs/fullchain.pem и privkey.pem (папка в .gitignore).
# Существующий сертификат не перезаписывает; принудительно: FORCE=1 bash scripts/gen_selfsigned.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; . ./.env; set +a; }

DIR=nginx/certs
mkdir -p "$DIR"
if [ -s "$DIR/fullchain.pem" ] && [ -s "$DIR/privkey.pem" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "Сертификат уже есть: $DIR/fullchain.pem (пересоздать: FORCE=1 make certs)"
  exit 0
fi

SAN="DNS:localhost,IP:127.0.0.1,IP:::1"
[ -n "${VPS_DOMAIN:-}" ] && SAN="$SAN,DNS:${VPS_DOMAIN}"
if [[ "${VPS_HOST:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then SAN="$SAN,IP:${VPS_HOST}"; fi

gen() {
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 -sha256 \
    -keyout "$1/privkey.pem" -out "$1/fullchain.pem" \
    -subj "/CN=localhost/O=Autello Barskiy (self-signed)" \
    -addext "subjectAltName=$SAN" \
    -addext "keyUsage=digitalSignature,keyEncipherment" \
    -addext "extendedKeyUsage=serverAuth" 2>/dev/null
}

if command -v openssl >/dev/null 2>&1 && gen "$DIR"; then
  :
else
  echo "Локального openssl нет (или он старый) — генерирую в контейнере alpine"
  docker run --rm -v "$PWD/$DIR:/certs" -e SAN="$SAN" alpine:3 sh -c \
    "apk add --no-cache openssl >/dev/null && openssl req -x509 -nodes -newkey rsa:2048 -days 825 -sha256 \
     -keyout /certs/privkey.pem -out /certs/fullchain.pem -subj '/CN=localhost/O=Autello Barskiy (self-signed)' \
     -addext \"subjectAltName=\$SAN\" -addext 'extendedKeyUsage=serverAuth'"
fi
chmod 600 "$DIR/privkey.pem"
echo "Готово: $DIR/fullchain.pem (SAN: $SAN)"
echo "Браузер предупредит о самоподписанном сертификате — это ожидаемо. На VPS: scripts/letsencrypt.sh"
