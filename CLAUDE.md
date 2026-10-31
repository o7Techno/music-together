# CLAUDE.md — правила проекта «Слушаем вместе»

Требования — только `SPEC.md`. План и прогресс — `PLAN.md`. Любое отступление от ТЗ или неочевидное
решение — запись в `DECISIONS.md` (что, почему, альтернативы).

## Стек
- **Backend** (`backend/`): Python 3.12, FastAPI, uvicorn, Pydantic v2, SQLAlchemy 2 async + Alembic,
  PostgreSQL 16, `yandex-music[async,crypto]`, structlog, cryptography. Зависимости — **uv**.
- **Frontend** (`frontend/`): React 19, TypeScript 6 (strict; TS 7 пока не поддержан typescript-eslint),
  Vite 8, Tailwind 4, Zustand, TanStack Query, dnd-kit, React Router. Тесты: Vitest + Testing Library,
  Playwright.
- **Infra:** Docker Compose (postgres, backend, caddy), GitHub Actions.

## Команды (из корня репозитория)
Корневой `package.json` — кросс-платформенный таск-раннер (на Windows нет `make`).

| Команда | Что делает |
|---|---|
| `npm run setup` | `uv sync` + `npm ci` во фронте |
| `npm run dev` | Postgres (docker) + бэкенд с `--reload` + Vite |
| `npm run dev:fake` | бэкенд + Vite без Postgres-контейнера |
| `npm run check` | все линтеры + тайпчекеры + unit/integration тесты |
| `npm run lint` / `typecheck` / `test` | по отдельности (суффиксы `:backend` / `:frontend`) |
| `npm run e2e` | Playwright: сам поднимает бэкенд (fake, SQLite) на :8011 и Vite на :5181 |
| `npm run gen:types` | JSON Schema из Pydantic → `frontend/src/shared/protocol/generated.ts` |
| `python scripts/gen_fake_audio.py` | тестовые треки FakeProvider (нужен ffmpeg; один раз после клона) |
| `npm run format` | ruff format/fix + prettier |

Бэкенд напрямую: `cd backend && uv run pytest`, `uv run mypy`, `uv run ruff check .`.
Фронт напрямую: `cd frontend && npm test`, `npm run lint`, `npm run typecheck`.

На этой машине `uv` лежит в `%APPDATA%\Python\Python312\Scripts` — в Bash-сессиях делать
`export PATH="$APPDATA/Python/Python312/Scripts:$PATH"`. В Python-скриптах на Windows —
`PYTHONIOENCODING=utf-8`. Фоновые dev-серверы на Windows оставляют дочерние процессы
(uvicorn reload-worker, vite): останавливать по PID слушателя порта, а не `taskkill /IM`.

Локальный запуск с настоящим Яндексом (без Docker, SQLite, вход по коду):
`cd backend && ENV=dev MUSIC_PROVIDER=yandex TOKEN_ENCRYPTION_KEYS=<fernet-ключ> DATABASE_URL=sqlite+aiosqlite:///./dev.db DB_AUTO_CREATE=true PUBLIC_ORIGIN=http://localhost:5173 uv run uvicorn app.main:app --port 8000`.
Vite запускать из `frontend/` как `./node_modules/.bin/vite --port 5173 --strictPort`: `npx` из другого
каталога поднимет его не там (404). Демон Docker на этой машине может не отвечать: образы проверяет CI
(job `docker`). Статус CI — badge `actions/workflows/ci.yml/badge.svg?branch=main`: анонимный лимит
GitHub API быстро кончается, логи job без прав недоступны, аннотации публичны.

## Грабли
- `yandex_music`: `make_client` не вызывает `init()`, `account_uid` пуст — методам коллекции передавать
  `user_id=self.uid`, иначе в URL уйдёт `None`. 403 библиотека считает `UnauthorizedError`, а
  `YandexProvider._call` запускает на него одноразовое обновление токена; 409 и прочие коды становятся
  `NetworkError` и повторяются. Для мутаций `_call` без правок не подходит.
- Любая новая версия `PlaybackState` вызывает `SyncEngine.applyState` (сброс контроллера, отмена старта).
  Не менять её без смены воспроизведения.
- `_dispatch` в `ws/endpoint.py` обрабатывает сообщения соединения по одному: долгий `await` задержит
  `ping` и `ready` этого клиента. Запросы к Яндексу держать вне `room.lock` и вне цикла чтения.
- `ApiModel` — `extra="forbid"`: откат кода после добавления поля в сохраняемое состояние даст
  `room_state_corrupted`. Новые поля — со значением по умолчанию.
- `ProviderFactory.for_user` создаёт новый `FakeProvider` на каждый вызов; состояния у него нет.
- Пользователи dev-логина всегда на FakeProvider, даже при `MUSIC_PROVIDER=yandex` (D-023).
- На Windows файлы коммитятся без бита исполнения: новые `scripts/*.sh` помечать
  `git update-index --chmod=+x`.
- Подсказку Starlette поставить сторонний пакет вместо `httpx` не выполнять (D-006).
- Токен Яндекса из локального окружения владельца на сервер не переносить: каждый входит сам.

## Прод
`docker-compose.yml` (db, backend, web=Caddy), `backend/Dockerfile`, `frontend/Dockerfile`, `Caddyfile`.
`.env` для сервера — `scripts/init-env.sh <домен>`. Бэкапы — `scripts/backup.sh`,
эксплуатация — `docs/operations.md`. CI job `docker` поднимает весь стек и проверяет его по HTTPS.

## Структура
```
backend/app/{api,ws,rooms,providers,auth,db,core}   backend/tests
frontend/src/{player,features,shared}               frontend/e2e
scripts/   docs/   .github/workflows/
```
- `rooms/` — чистая доменная логика (без I/O): PlaybackState, очередь, актор комнаты. Время внедряется.
- `providers/` — `MusicProvider` (yandex, fake). Весь код `yandex_music` — **только** здесь.
- `frontend/src/player/` — движок синхронизации на чистом TS без React/DOM; часы, аудиоэлемент и
  планировщик внедряются через интерфейсы, тестируется в Vitest без браузера.

## Тесты
- Бэкенд unit — домен на FakeClock/FakeTimers (`tests/test_room.py`), интеграционные — живой uvicorn
  в потоке + `websockets`/`httpx` (`tests/live.py`), SQLite во временном каталоге.
- Фронт unit — движок синхронизации на FakeClock/FakeScheduler/FakeDeck (`src/player/testing.ts`).
- E2E — `frontend/e2e`, хук `window.__syncProbe()`; замер синхрона пишет `sync-stats.json`.

## Соглашения
- Conventional Commits, маленькие логические коммиты. Фаза закрыта только при зелёных
  `npm run check` + e2e.
- Python: mypy strict, ruff (конфиг в `backend/pyproject.toml`), `from __future__ import annotations`,
  без `# type: ignore` без комментария-обоснования. Ошибки домена — свои исключения из `core/errors.py`.
- TS: strict + `noUncheckedIndexedAccess`, eslint `strictTypeChecked`, без `any`; импорт через `@/`.
- Протокол WS: Pydantic-модели на бэке — источник истины; TS-типы генерируются (`npm run gen:types`),
  руками не редактировать `frontend/src/shared/protocol/generated.ts`.
- Время: на сервере `time.monotonic()` для интервалов, epoch ms для протокола; на клиенте
  `performance.now() + performance.timeOrigin`.
- Тексты UI — на русском. Код, идентификаторы — на английском; комментарии и docstring — по-русски.

## Секреты
Никогда не коммитить токены и ключи. Только `.env.example`. Токен Яндекса не логируется
(structlog-процессор `mask_secrets`), не отдаётся на фронт. `scripts/.spike-out/` в .gitignore.
