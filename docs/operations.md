# Эксплуатация

## Сервисы
`docker compose ps` — три сервиса: `db` (PostgreSQL 16), `backend` (FastAPI, миграции при старте),
`web` (Caddy: статика + HTTPS + reverse proxy). Данные — в томах `pgdata`, `caddy_data` (сертификаты).

- Логи: `docker compose logs -f backend` (JSON, с `request_id` / `room` / `conn_id`; токены маскируются).
- Здоровье: `https://<домен>/health` (процесс жив), `https://<домен>/ready` (БД доступна).
- Перезапуск без потери комнат: `docker compose restart backend` — состояние комнат сохраняется,
  клиенты получают «переподключитесь» (1012) и сами возвращаются; после рестарта комнаты на паузе.

## Бэкапы

```bash
./scripts/backup.sh                 # backups/music-YYYYmmdd-HHMMSS.dump, хранятся последние 14
KEEP=30 ./scripts/backup.sh         # хранить 30
```

Ежедневно по cron (от пользователя с доступом к docker):

```cron
15 4 * * * cd /opt/music-together && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Копируйте `backups/` за пределы сервера (rsync/rclone в объектное хранилище).

### Восстановление

```bash
docker compose stop backend
docker compose exec -T db pg_restore -U music -d music --clean --if-exists --no-owner < backups/music-20261101-041500.dump
docker compose start backend
```

Проверка бэкапа без боевой БД: поднять отдельный контейнер `postgres:16-alpine`, сделать
`pg_restore` в него и `SELECT count(*) FROM rooms;`.

## Ключи

- **Ротация ключа шифрования токенов.** Сгенерировать новый ключ и поставить его **первым**:
  `TOKEN_ENCRYPTION_KEYS=<новый>,<старый>` → `docker compose up -d`. Старые токены читаются, новые
  шифруются новым ключом. Пользователи при следующем входе получат токен, зашифрованный новым ключом;
  когда старых записей не останется (или через срок жизни токенов — год), старый ключ можно убрать.
- **Смена `SESSION_SECRET`** разлогинит всех (сессии станут недействительны).

## Обновление

```bash
git pull
docker compose up -d --build
docker image prune -f
```

## Sentry (необязательно)

`SENTRY_DSN` (бэкенд) и `SENTRY_FRONTEND_DSN` (фронт) в `.env`. Персональные данные, cookie и токены
в события не попадают (фильтр `before_send`).
