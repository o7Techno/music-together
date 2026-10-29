# Бэкенд «Слушаем вместе». Сборка из корня репозитория:
#   docker build -f backend/Dockerfile -t music-together-backend .
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Сначала зависимости — слой кешируется, пока не меняется uv.lock.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
# Тестовые треки FakeProvider (если сгенерированы) — для демо без аккаунта Яндекса.
COPY backend/fake_media ./fake_media

RUN useradd --system --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# Миграции при старте, затем uvicorn: заголовки прокси от Caddy, лимит WS-сообщений 64 КБ,
# корректное завершение (комнаты сохраняются, клиенты получают «переподключитесь»).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --ws-max-size 65536 --timeout-graceful-shutdown 15"]
