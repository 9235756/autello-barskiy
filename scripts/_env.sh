# Общий хелпер для bash-скриптов: переходит в корень проекта и загружает .env.
# Подключение:  source "$(dirname "$0")/_env.sh"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
  echo "Нет файла .env — выполните: make init (или cp example.env .env)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

MOCK_MODE="${MOCK_MODE:-true}"
# Раскрываем ~ в пути к ключу
VPS_SSH_KEY_PATH="${VPS_SSH_KEY_PATH/#\~/$HOME}"

is_mock() { [ "$MOCK_MODE" = "true" ]; }
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
mock() { printf '\033[0;36m[MOCK на сервере выполнилось бы]\033[0m %s\n' "$*"; }
