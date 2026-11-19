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
  mock "ssh $VPS_USER@$VPS_HOST 'cd $DEST && chmod 600 .env && cd registry && ./create-user.sh \$REGISTRY_USER *** && cd .. && docker compose pull && docker compose up -d'"
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
  -e "ssh -i $VPS_SSH_KEY_PATH" ./ "$VPS_USER@$VPS_HOST:$DEST/"

say "Создаю пользователя реестра и поднимаю стек"
"${SSH[@]}" "bash -s" <<EOF
set -euo pipefail
cd '$DEST'
chmod 600 .env
mkdir -p /root/.docker && [ -f /root/.docker/config.json ] || echo '{}' > /root/.docker/config.json
chmod +x registry/create-user.sh scripts/*.sh
./registry/create-user.sh '$REGISTRY_USER' '$REGISTRY_PASSWORD'
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
EOF

say "Готово. Откройте:"
echo "  http://$VPS_HOST:$HTTP_PORT            — сайт"
echo "  http://$VPS_HOST:$REGISTRY_UI_PORT     — Registry UI"
echo "  http://$VPS_HOST:$PGADMIN_PORT         — pgAdmin"
warn "Без TLS пароли летят открытым текстом — см. README, раздел «TLS для реестра»."
