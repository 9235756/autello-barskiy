#!/usr/bin/env bash
# Шаг 3 задания: установка Docker CE + плагина docker compose на Ubuntu 22.04.
# Официальный способ: репозиторий download.docker.com (не docker.io из Ubuntu,
# не старый docker-compose v1). Идемпотентно — если всё стоит, ничего не делает.
#
#   MOCK_MODE=true  — проверяет локальные docker и docker compose
#   MOCK_MODE=false — выполняет установку на VPS по SSH
#   ./install_docker.sh --local — выполнить установку на ЭТОЙ машине (когда скрипт запущен прямо на VPS)
set -euo pipefail
source "$(dirname "$0")/_env.sh"

REMOTE_INSTALL=$(cat <<'EOF'
set -euo pipefail
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  echo "Docker уже установлен: $(docker --version)"; docker compose version; exit 0
fi
. /etc/os-release
[ "$ID" = "ubuntu" ] || { echo "Ожидалась Ubuntu, а тут $PRETTY_NAME"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
# Убираем конфликтующие пакеты (в т.ч. старый docker-compose v1)
for p in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  apt-get remove -y "$p" >/dev/null 2>&1 || true
done
apt-get update -y
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version
docker compose version
docker run --rm hello-world >/dev/null && echo "hello-world: OK"
EOF
)

if [ "${1:-}" = "--local" ]; then
  [ "$(id -u)" -eq 0 ] || { echo "Запустите от root: sudo $0 --local"; exit 1; }
  bash -c "$REMOTE_INSTALL"; exit 0
fi

if is_mock; then
  say "MOCK_MODE=true — проверяю локальный Docker"
  command -v docker >/dev/null || { echo "docker не найден — установите Docker Desktop / Docker Engine"; exit 1; }
  docker --version
  docker compose version || { echo "Нет плагина docker compose"; exit 1; }
  if command -v docker-compose >/dev/null; then
    warn "Найден и старый docker-compose ($(command -v docker-compose)). В проекте используем только 'docker compose'."
  fi
  docker info --format 'Docker Engine {{.ServerVersion}} — запущен' || { echo "Docker daemon не запущен"; exit 1; }
  mock "установка Docker CE на $VPS_USER@$VPS_HOST:"
  echo "$REMOTE_INSTALL" | sed 's/^/    /'
  exit 0
fi

say "Устанавливаю Docker на $VPS_USER@$VPS_HOST"
ssh -i "$VPS_SSH_KEY_PATH" "$VPS_USER@$VPS_HOST" "bash -s" <<<"$REMOTE_INSTALL"
