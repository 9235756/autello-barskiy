#!/usr/bin/env bash
# Боевой режим: заливает проект на VPS (rsync) и поднимает стек там.
#   ./scripts/deploy_to_vps.sh
# Требует: setup_ssh_key.sh и install_docker.sh уже выполнены, .env заполнен
# (VPS_HOST, пароли; REGISTRY_HOST = IP или домен VPS).
set -euo pipefail
source "$(dirname "$0")/_env.sh"

DEST="${VPS_PROJECT_DIR:-/opt/autello_barskiy}"
SSH=(ssh -i "$VPS_SSH_KEY_PATH" "$VPS_USER@$VPS_HOST")

if is_mock; then
  say "MOCK_MODE=true — деплой на реальный сервер не выполняется."
  mock "rsync -az --delete --exclude mock/ --exclude reports/ --exclude .git/ ./ $VPS_USER@$VPS_HOST:$DEST/"
  mock "ssh $VPS_USER@$VPS_HOST 'cd $DEST && chmod 600 .env && ./registry/create-user.sh ... && bash scripts/gen_secret.sh && bash scripts/gen_selfsigned.sh && docker compose up -d --build'"
  say "Локальный эквивалент: make up"
  exit 0
fi

[ "$REGISTRY_HOST" = "localhost" ] && warn "REGISTRY_HOST=localhost — для VPS укажите его IP или домен в .env"

say "Синхронизирую проект в $VPS_USER@$VPS_HOST:$DEST"
"${SSH[@]}" "mkdir -p '$DEST'"
# .env едет на сервер (там он нужен), mock/ и reports/ — нет. htpasswd пересоздаём на сервере.
rsync -az --delete \
  --exclude '.git/' --exclude 'mock/' --exclude 'reports/' --exclude '.DS_Store' \
  --exclude 'registry/auth/htpasswd' \
  --exclude 'nginx/certs/' --exclude 'nginx/certbot-www/' --exclude 'node_modules/' \
  -e "ssh -i $VPS_SSH_KEY_PATH" ./ "$VPS_USER@$VPS_HOST:$DEST/"

say "Создаю пользователя реестра и поднимаю стек"
"${SSH[@]}" "bash -s" <<EOF
set -euo pipefail
cd '$DEST'
chmod 600 .env
mkdir -p /root/.docker && [ -f /root/.docker/config.json ] || echo '{}' > /root/.docker/config.json
chmod +x registry/create-user.sh scripts/*.sh
./registry/create-user.sh '$REGISTRY_USER' '$REGISTRY_PASSWORD'
# Часть 3: секрет JWT и временный самоподписанный сертификат (если Let's Encrypt ещё не получен)
bash scripts/gen_secret.sh
bash scripts/gen_selfsigned.sh
docker compose pull --ignore-buildable --ignore-pull-failures
# Защищённый режим (пункт 5): наружу только nginx
docker compose up -d --build --remove-orphans
docker compose ps
EOF

say "Готово. Откройте:"
echo "  https://$VPS_HOST/             — сайт (http → 301 на https)"
echo "  https://$VPS_HOST/admin        — админка"
echo "  Сертификат Let's Encrypt: ssh на сервер → bash scripts/letsencrypt.sh (нужен VPS_DOMAIN)"
echo "  pgAdmin и registry в защищённом режиме выключены (профиль admin-tools)"
