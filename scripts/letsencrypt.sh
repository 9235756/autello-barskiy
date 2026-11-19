#!/usr/bin/env bash
# Сертификат Let's Encrypt для реального VPS (certbot, метод webroot). Запускать НА СЕРВЕРЕ.
#
# Требования:
#   - домен (VPS_DOMAIN в .env) с A-записью на IP сервера;
#   - открыты порты 80 и 443 (ufw allow 80,443/tcp);
#   - стек уже запущен (make secure) с самоподписанным сертификатом: nginx отдаёт
#     /.well-known/acme-challenge/ из nginx/certbot-www даже в secure-режиме.
#
# Что делает:
#   1) certbot (в контейнере certbot/certbot) кладёт файл-подтверждение в nginx/certbot-www;
#   2) Let's Encrypt проверяет его по http://<домен>/.well-known/acme-challenge/...;
#   3) сертификат ложится в nginx/certs/live/<домен>/;
#   4) скрипт прописывает SSL_CERT_PATH / SSL_KEY_PATH в .env и перезапускает nginx.
# Продление: добавьте в crontab сервера
#   0 3 * * 1  cd /opt/autello_barskiy && bash scripts/letsencrypt.sh --renew
set -euo pipefail
source "$(dirname "$0")/_env.sh"

if is_mock; then
  mock "docker run certbot/certbot certonly --webroot -w nginx/certbot-www -d ${VPS_DOMAIN:-<домен>} -m ${LETSENCRYPT_EMAIL:-<email>}"
  warn "MOCK_MODE=true: Let's Encrypt не выдаёт сертификаты для localhost. Локально используется make certs (самоподписанный)."
  exit 0
fi
[ -n "${VPS_DOMAIN:-}" ] || { echo "Задайте VPS_DOMAIN в .env (домен с A-записью на этот сервер)"; exit 1; }
[ -n "${LETSENCRYPT_EMAIL:-}" ] && [ "$LETSENCRYPT_EMAIL" != "you@example.com" ] || { echo "Задайте LETSENCRYPT_EMAIL в .env"; exit 1; }

mkdir -p nginx/certbot-www nginx/certs
CERTBOT=(docker run --rm -v "$PWD/nginx/certs:/etc/letsencrypt" -v "$PWD/nginx/certbot-www:/var/www/certbot" certbot/certbot)

if [ "${1:-}" = "--renew" ]; then
  say "Продление сертификатов"
  "${CERTBOT[@]}" renew --webroot -w /var/www/certbot --quiet
else
  say "Получаю сертификат для ${VPS_DOMAIN}"
  "${CERTBOT[@]}" certonly --webroot -w /var/www/certbot -d "$VPS_DOMAIN" \
    --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email --non-interactive
fi

CERT="./nginx/certs/live/${VPS_DOMAIN}/fullchain.pem"
KEY="./nginx/certs/live/${VPS_DOMAIN}/privkey.pem"
# live/<домен>/*.pem — симлинки на ../../archive/...; Docker при монтировании файла
# разрешает симлинк на хосте и монтирует сам сертификат. После renew — пересоздаём nginx.
tmp="$(mktemp)"
awk -v c="$CERT" -v k="$KEY" '/^SSL_CERT_PATH=/{print "SSL_CERT_PATH=" c; next} /^SSL_KEY_PATH=/{print "SSL_KEY_PATH=" k; next} {print}' .env > "$tmp"
cat "$tmp" > .env; rm -f "$tmp"
say "SSL_CERT_PATH=$CERT"
docker compose up -d --force-recreate nginx
say "Готово: https://${VPS_DOMAIN}"
