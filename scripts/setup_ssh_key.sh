#!/usr/bin/env bash
# Шаг 2 задания: вход root по SSH-ключу и отключение входа по паролю.
#
# Боевой режим (MOCK_MODE=false):
#   1) создаёт ключ ed25519, если его нет;
#   2) ssh-copy-id на VPS (спросит пароль root из «Инструкции» хостинга — один раз);
#   3) проверяет вход по ключу и ТОЛЬКО ПОСЛЕ ЭТОГО отключает вход по паролю;
#   4) добавляет Host autello-vps в ~/.ssh/config.
# Эмуляция (MOCK_MODE=true): ~/.ssh не трогаем, печатаем команды, которые выполнились бы.
set -euo pipefail
source "$(dirname "$0")/_env.sh"

HOST_ALIAS="autello-vps"
SSHD_DROPIN="/etc/ssh/sshd_config.d/99-autello-hardening.conf"
REMOTE_HARDEN=$(cat <<EOF
set -e
cat > $SSHD_DROPIN <<'CONF'
# Autello: только вход по ключу
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
CONF
# На Ubuntu 22.04 cloud-образах 50-cloud-init.conf может включать пароли — гасим его
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config.d/50-cloud-init.conf 2>/dev/null || true
sshd -t
systemctl reload ssh
sshd -T | grep -E '^(passwordauthentication|permitrootlogin) '
EOF
)

HOST_BLOCK="Host $HOST_ALIAS
    HostName $VPS_HOST
    User $VPS_USER
    IdentityFile $VPS_SSH_KEY_PATH
    IdentitiesOnly yes"

if is_mock; then
  say "MOCK_MODE=true — эмуляция. Реальный сервер и ~/.ssh не затрагиваются."
  KEY="$PROJECT_ROOT/mock/id_ed25519_mock"
  mkdir -p mock
  if [ -f "$VPS_SSH_KEY_PATH" ]; then
    say "Ключ уже есть: $VPS_SSH_KEY_PATH — генерировать не нужно"
  elif [ ! -f "$KEY" ]; then
    ssh-keygen -t ed25519 -N "" -C "autello-mock" -f "$KEY" >/dev/null
    say "Сгенерирован учебный ключ: mock/id_ed25519_mock (в боевом режиме — $VPS_SSH_KEY_PATH)"
  fi
  mock "ssh-copy-id -i ${VPS_SSH_KEY_PATH}.pub $VPS_USER@$VPS_HOST"
  mock "ssh -o BatchMode=yes -i $VPS_SSH_KEY_PATH $VPS_USER@$VPS_HOST true   # проверка входа по ключу"
  echo "$REMOTE_HARDEN" | sed 's/^/    /'
  printf '%s\n' "$HOST_BLOCK" > mock/ssh_config_host_entry
  say "Host-запись сохранена в mock/ssh_config_host_entry (в боевом режиме — в ~/.ssh/config)"
  exit 0
fi

# ---------- Боевой режим ----------
command -v ssh-copy-id >/dev/null || { echo "Нужен ssh-copy-id (macOS/Linux: входит в OpenSSH)"; exit 1; }

if [ ! -f "$VPS_SSH_KEY_PATH" ]; then
  say "Создаю ключ $VPS_SSH_KEY_PATH"
  mkdir -p "$(dirname "$VPS_SSH_KEY_PATH")" && chmod 700 "$(dirname "$VPS_SSH_KEY_PATH")"
  ssh-keygen -t ed25519 -C "autello-$(whoami)" -f "$VPS_SSH_KEY_PATH"
fi

say "Копирую публичный ключ на $VPS_USER@$VPS_HOST (введите пароль root из «Инструкции»)"
ssh-copy-id -i "${VPS_SSH_KEY_PATH}.pub" -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_HOST"

say "Проверяю вход по ключу без пароля"
if ! ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$VPS_SSH_KEY_PATH" "$VPS_USER@$VPS_HOST" true; then
  echo "Вход по ключу НЕ работает — пароль НЕ отключаю, чтобы не потерять доступ." >&2
  exit 1
fi

say "Отключаю вход по паролю"
ssh -i "$VPS_SSH_KEY_PATH" "$VPS_USER@$VPS_HOST" "bash -s" <<<"$REMOTE_HARDEN"

say "Повторная проверка входа по ключу после reload sshd"
ssh -o BatchMode=yes -i "$VPS_SSH_KEY_PATH" "$VPS_USER@$VPS_HOST" 'echo "OK: $(hostname)"'

if ! grep -q "^Host $HOST_ALIAS\$" "$HOME/.ssh/config" 2>/dev/null; then
  cp "$HOME/.ssh/config" "$HOME/.ssh/config.bak.autello" 2>/dev/null || true
  printf '\n%s\n' "$HOST_BLOCK" >> "$HOME/.ssh/config"
  chmod 600 "$HOME/.ssh/config"
  say "Добавлен Host $HOST_ALIAS в ~/.ssh/config — теперь: ssh $HOST_ALIAS"
else
  warn "Host $HOST_ALIAS уже есть в ~/.ssh/config — не трогаю"
fi
