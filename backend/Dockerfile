# Backend Autello: FastAPI + SQLAlchemy 2 + psycopg 3
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BACKEND_INTERNAL_PORT=8000

WORKDIR /srv

# Сначала зависимости — этот слой кешируется, пока не меняется requirements.txt
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Не запускаем приложение от root
RUN useradd --system --uid 10001 app
USER app

EXPOSE 8000

# Healthcheck ходит в /api/health, а тот делает SELECT 1 к БД:
# контейнер healthy, только если жив и сам backend, и связь с postgres
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import os,sys,urllib.request; p=os.getenv('BACKEND_INTERNAL_PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/api/health', timeout=2).status == 200 else 1)"

# 0.0.0.0 — слушаем все интерфейсы контейнера (127.0.0.1 nginx бы не увидел).
# --proxy-headers: доверяем X-Forwarded-* от nginx (реальный IP клиента и схема)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_INTERNAL_PORT} --proxy-headers --forwarded-allow-ips '*'"]
