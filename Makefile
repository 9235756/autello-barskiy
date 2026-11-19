# Autello — цели сборки (части 1–3). Windows: команды PowerShell — в README, раздел «PowerShell».
SHELL  := /bin/bash
PYTHON ?= python3

# Подтягиваем .env, если он уже есть (POSTGRES_*, REGISTRY_*, DEMO_ADMIN_* и т.п.)
-include .env
export

# dev = базовый compose (secure) + docker-compose.dev.yml + профиль admin-tools (pgAdmin, registry)
COMPOSE_DEV    := docker compose -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_SECURE := docker compose
PSQL           := docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) -d $(POSTGRES_DB)

.PHONY: init secret certs dev secure build-front seed test-sql backfill e2e pytest check logs logs-nginx \
        ps down clean all mock-vps user ensure-user leads gpt push wait

# ---------- Подготовка ----------
init:
	@if [ -f .env ]; then echo ".env уже есть — не трогаю"; else cp example.env .env && echo "Создан .env из example.env — замените пароли"; fi

# .env + новые переменные части 3 + SECRET_KEY (openssl rand -hex 32)
secret:
	bash scripts/gen_secret.sh

# Самоподписанный сертификат → nginx/certs/ (на VPS: bash scripts/letsencrypt.sh)
certs:
	bash scripts/gen_selfsigned.sh

mock-vps:
	$(PYTHON) scripts/mock_vps.py

# Пользователь реестра (htpasswd). Нужен контейнеру registry из части 1
user:
	cd registry && ./create-user.sh "$(REGISTRY_USER)" "$(REGISTRY_PASSWORD)"

ensure-user:
	@[ -s registry/auth/htpasswd ] || $(MAKE) user

# ---------- Режимы запуска ----------
# Ждём, пока backend и nginx станут healthy
wait:
	@echo "Жду, пока backend и nginx станут healthy..."
	@for i in $$(seq 1 60); do \
		b=$$(docker inspect -f '{{.State.Health.Status}}' backend 2>/dev/null); \
		n=$$(docker inspect -f '{{.State.Health.Status}}' nginx 2>/dev/null); \
		[ "$$b" = healthy ] && [ "$$n" = healthy ] && echo "backend: $$b, nginx: $$n" && exit 0; sleep 2; \
	done; echo "Не дождался healthy (backend=$$b nginx=$$n). Смотрите: docker logs backend / docker logs nginx"; exit 1

# Разработка: Swagger на :8000/docs, pgAdmin :5050, registry, http на 80 и https на 443
dev: ensure-user certs
	@[ -f frontend/dist/index.html ] || $(MAKE) build-front
	COMPOSE_PROFILES=admin-tools $(COMPOSE_DEV) up -d --build --remove-orphans
	@$(MAKE) --no-print-directory wait
	@echo "dev: http://localhost  https://localhost  Swagger http://localhost:$(BACKEND_DEV_PORT)/docs  pgAdmin http://localhost:$(PGADMIN_PORT)"

# Защищённый режим: наружу только nginx (80→301, 443, 8000/5432 → 403); pgAdmin и registry выключены
secure: certs
	@[ -f frontend/dist/index.html ] || $(MAKE) build-front
	-docker compose --profile admin-tools stop pgadmin registry registry-ui 2>/dev/null
	-docker compose --profile admin-tools rm -f pgadmin registry registry-ui 2>/dev/null
	$(COMPOSE_SECURE) up --build -d --remove-orphans
	@$(MAKE) --no-print-directory wait
	@echo "secure: https://localhost (http → 301), :$(STUB_BACKEND_PORT) и :$(STUB_POSTGRES_PORT) → 403, /docs → 404"

# Совместимость с частью 2
up: dev

# ---------- Фронтенд ----------
# Локальный npm, а если его нет — одноразовый контейнер node:20-alpine
build-front:
	@if command -v npm >/dev/null 2>&1; then \
		echo "npm найден — собираю локально"; cd frontend && npm ci --no-audit --no-fund && npm run build; \
	else \
		echo "npm не найден — собираю в контейнере node:20-alpine"; docker compose --profile tools run --rm frontend-build; \
	fi

# ---------- Данные ----------
seed:
	$(PYTHON) scripts/seed_services.py

# 10 тестовых заявок (4 🔥 / 3 🌤 / 3 ❄️). Нужны услуги из make seed
test-sql:
	$(PSQL) < sql/test_applications.sql

# ~300 исторических визитов за 30 дней для «Статистики пользователей»
backfill:
	$(PYTHON) scripts/backfill_metrics.py

leads:
	$(PYTHON) scripts/simulate_leads.py

gpt:
	$(PYTHON) scripts/mock_gpt.py --last 3

# ---------- Тесты ----------
# Playwright в контейнере (dev-режим). В эмуляции перед тестом очищаем admins,
# чтобы проверить кнопку «Зарегистрироваться» на «чистой» БД; демо-админ создаётся заново.
# Один spec: make e2e E2E_ARGS=services_crud.spec.ts
e2e:
	@if [ "$(MOCK_MODE)" = "true" ] && [ -z "$(E2E_ARGS)" ]; then \
		echo "MOCK_MODE=true: очищаю таблицу admins для теста регистрации"; \
		$(PSQL) -qc "DELETE FROM admins"; \
	fi
	mkdir -p reports/screens
	$(COMPOSE_DEV) --profile tools run --rm e2e

pytest:
	docker compose run --rm --no-deps -T backend python -m pytest -q -p no:cacheprovider tests

check:
	bash scripts/check.sh

# ---------- Обслуживание ----------
logs:
	docker logs -f backend

logs-nginx:
	docker logs -f nginx

ps:
	docker compose --profile admin-tools ps

down:
	docker compose --profile admin-tools --profile tools down

# Полная очистка: контейнеры + тома (данные БД и реестра) + генерируемые артефакты
clean:
	docker compose --profile admin-tools --profile tools down -v --remove-orphans
	rm -rf mock/* reports/*

# Публикация образа backend в локальный registry — Watchtower подхватит новую версию (dev-режим)
push:
	@echo "$(REGISTRY_PASSWORD)" | docker login $(REGISTRY_HOST):$(REGISTRY_PORT) -u "$(REGISTRY_USER)" --password-stdin
	docker compose build backend
	docker compose push backend

# Полный прогон части 3: от секрета до отчёта в защищённом режиме
all: secret certs dev build-front seed test-sql backfill e2e pytest secure check
