# Фронтенд + Caddy (статика, reverse proxy на бэкенд, автоматический HTTPS).
# Сборка из корня репозитория:
#   docker build -f frontend/Dockerfile -t music-together-web .
FROM node:24-alpine AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/frontend/dist /srv
