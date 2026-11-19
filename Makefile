# Autello — цели сборки (части 1 и 2). Windows: см. README, раздел «PowerShell».
SHELL  := /bin/bash
PYTHON ?= python3

# Подтягиваем .env, если он уже есть (для REGISTRY_USER / REGISTRY_PASSWORD и т.п.)
-include .env
export

.PHONY: init mock-vps user ensure-user build-front up seed leads e2e check logs logs-nginx ps push gpt down clean all

# ---------- Подготовка ----------
init:
	@if [ -f .env ]; then echo ".env уже есть — не трогаю"; else cp example.env .env && echo "Создан .env из example.env — замените пароли"; fi

mock-vps:
	$(PYTHON) scripts/mock_vps.py

# Пользователь реестра (htpasswd). Нужен контейнеру registry из части 1
user:
	cd registry && ./create-user.sh "$(REGISTRY_USER)" "$(REGISTRY_PASSWORD)"

ensure-user:
	@[ -s registry/auth/htpasswd ] || $(MAKE) user

# ---------- Часть 2 ----------
# Сборка фронта: локальный npm, а если его нет — одноразовый контейнер node:20-alpine
build-front:
	@if command -v npm >/dev/null 2>&1; then \
		echo "npm найден — собираю локально"; cd frontend && npm ci --no-audit --no-fund && npm run build; \
	else \
		echo "npm не найден — собираю в контейнере node:20-alpine"; docker compose --profile tools run --rm frontend-build; \
	fi

up:
	@[ -f frontend/dist/index.html ] || { echo "Нет frontend/dist — сначала make build-front"; exit 1; }
	docker compose up -d --build --remove-orphans
	@echo "Жду, пока backend и nginx станут healthy..."
	@for i in $$(seq 1 45); do \
		b=$$(docker inspect -f '{{.State.Health.Status}}' backend 2>/dev/null); \
		n=$$(docker inspect -f '{{.State.Health.Status}}' nginx 2>/dev/null); \
		[ "$$b" = healthy ] && [ "$$n" = healthy ] && echo "backend: $$b, nginx: $$n" && exit 0; sleep 2; \
	done; echo "Не дождался healthy (backend=$$b nginx=$$n). Смотрите: docker logs backend / docker logs nginx"; exit 1

seed:
	$(PYTHON) scripts/seed_services.py

leads:
	$(PYTHON) scripts/simulate_leads.py

e2e:
	docker compose --profile tools run --rm e2e

check:
	bash scripts/check.sh

gpt:
	$(PYTHON) scripts/mock_gpt.py --last 3

# Публикация образа backend в локальный registry — Watchtower подхватит новую версию
push:
	@echo "$(REGISTRY_PASSWORD)" | docker login $(REGISTRY_HOST):$(REGISTRY_PORT) -u "$(REGISTRY_USER)" --password-stdin
	docker compose build backend
	docker compose push backend

logs:
	docker logs -f backend

logs-nginx:
	docker logs -f nginx

ps:
	docker compose ps

down:
	docker compose down

# Полная очистка: контейнеры + тома (данные БД и реестра) + генерируемые артефакты
clean:
	docker compose down -v --remove-orphans
	rm -rf mock/* reports/*

all: init ensure-user build-front up seed leads e2e check
