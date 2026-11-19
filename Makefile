# Autello — цели сборки. Windows: см. README, раздел «PowerShell».
SHELL  := /bin/bash
PYTHON ?= python3

# Подтягиваем .env, если он уже есть (для REGISTRY_USER / REGISTRY_PASSWORD)
-include .env
export

.PHONY: init mock-vps user up seed check down clean all ps logs

init:
	@if [ -f .env ]; then echo ".env уже есть — не трогаю"; else cp example.env .env && echo "Создан .env из example.env — замените пароли"; fi

mock-vps:
	$(PYTHON) scripts/mock_vps.py

user:
	cd registry && ./create-user.sh "$(REGISTRY_USER)" "$(REGISTRY_PASSWORD)"

up:
	docker compose up -d
	@echo "Жду, пока postgres станет healthy..."
	@for i in $$(seq 1 30); do \
		s=$$(docker inspect -f '{{.State.Health.Status}}' $$(docker compose ps -q postgres) 2>/dev/null); \
		[ "$$s" = "healthy" ] && echo "postgres: healthy" && exit 0; sleep 2; \
	done; echo "postgres не стал healthy за 60 c — смотрите: docker compose logs postgres"; exit 1

seed:
	$(PYTHON) scripts/seed_leads.py

check:
	bash scripts/check.sh

ps:
	docker compose ps

logs:
	docker compose logs --tail=50

down:
	docker compose down

# Полная очистка: контейнеры + тома (данные БД и реестра) + генерируемые артефакты
clean:
	docker compose down -v --remove-orphans
	rm -rf mock/* reports/*

all: init mock-vps user up seed check
