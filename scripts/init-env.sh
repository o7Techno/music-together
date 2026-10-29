#!/usr/bin/env sh
# Создать .env для продакшена из .env.example со случайными секретами.
#   ./scripts/init-env.sh music.example.com admin@example.com
set -eu
cd "$(dirname "$0")/.."
DOMAIN="${1:?Укажите домен: ./scripts/init-env.sh music.example.com [email]}"
EMAIL="${2:-}"
if [ -e .env ]; then
  echo ".env уже существует — не перезаписываю" >&2
  exit 1
fi
rand() { openssl rand -base64 "$1" | tr -d '\n=' | tr '+/' '-_'; }
SESSION_SECRET=$(rand 48)
POSTGRES_PASSWORD=$(rand 24)
# Fernet-ключ: base64url от 32 случайных байт (с паддингом).
FERNET_KEY=$(openssl rand -base64 32 | tr -d '\n' | tr '+/' '-_')
sed \
  -e "s|^ENV=.*|ENV=prod|" \
  -e "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" \
  -e "s|^ACME_EMAIL=.*|ACME_EMAIL=$EMAIL|" \
  -e "s|^PUBLIC_ORIGIN=.*|PUBLIC_ORIGIN=https://$DOMAIN|" \
  -e "s|^SESSION_SECRET=.*|SESSION_SECRET=$SESSION_SECRET|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" \
  -e "s|^TOKEN_ENCRYPTION_KEYS=.*|TOKEN_ENCRYPTION_KEYS=$FERNET_KEY|" \
  .env.example > .env
chmod 600 .env
echo "Готово: .env для https://$DOMAIN (секреты сгенерированы, файл доступен только владельцу)."
