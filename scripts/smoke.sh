#!/usr/bin/env bash
# Smoke-тест поднятого `docker compose` стека по HTTPS (FakeProvider, DOMAIN=localhost).
# В GitHub Actions ошибки уходят в аннотации (видны без доступа к логам).
#   ./scripts/smoke.sh [base_url]
set -uo pipefail

BASE="${1:-https://localhost}"
JAR="$(mktemp)"
FAILED=0

annotate() {
  local title="$1" body="$2"
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    # Переводы строк в аннотации кодируются как %0A.
    body="${body//'%'/'%25'}"
    body="${body//$'\n'/'%0A'}"
    echo "::error title=Smoke: ${title}::${body:0:6000}"
  else
    printf 'FAIL %s\n%s\n' "$title" "$body"
  fi
}

# check <название> <ожидаемая подстрока или пусто> <curl args...>
check() {
  local name="$1" expect="$2"
  shift 2
  local out code
  out="$(curl -sSk --max-time 15 -w '\nHTTP %{http_code}' "$@" 2>&1)"
  code=$?
  if [ $code -ne 0 ] || ! grep -q "HTTP 2" <<<"$out" || { [ -n "$expect" ] && ! grep -qi -- "$expect" <<<"$out"; }; then
    annotate "$name" "curl exit=$code expect='$expect'"$'\n'"$out"
    FAILED=1
  else
    echo "ok  $name"
  fi
}

ORIGIN=(-H "Origin: $BASE" -H "Content-Type: application/json")

check "health" '"ok"' "$BASE/health"
check "ready" '"ok"' "$BASE/ready"
check "index.html" "<title>Слушаем вместе</title>" "$BASE/"
check "security headers" "content-security-policy" -I "$BASE/"
check "dev login" '"displayName"' -c "$JAR" "${ORIGIN[@]}" -d '{"name":"CI"}' "$BASE/api/auth/dev-login"
check "create room" '"slug"' -b "$JAR" "${ORIGIN[@]}" -d '{"name":"CI room"}' "$BASE/api/rooms"
check "search" "fake-3" -b "$JAR" "$BASE/api/search?q=%D0%BC%D0%B8%D0%BD%D1%83%D1%82%D0%B0"
# check_status <название> <ожидаемый HTTP-код> <curl args...>
check_status() {
  local name="$1" want="$2"
  shift 2
  local got
  got="$(curl -sk --max-time 15 -o /dev/null -w '%{http_code}' "$@")"
  if [ "$got" != "$want" ]; then
    annotate "$name" "expected HTTP $want, got $got"
    FAILED=1
  else
    echo "ok  $name"
  fi
}

check_status "csrf rejects foreign origin" 403 -b "$JAR" -H "Origin: https://evil.example" \
  -H "Content-Type: application/json" -d '{"name":"x"}' "$BASE/api/rooms"
check_status "anonymous gets 401" 401 "$BASE/api/rooms"

if [ "${SMOKE_RESTART:-}" = "1" ]; then
  docker compose restart backend >/dev/null
  for _ in $(seq 1 30); do curl -fsSk --max-time 3 "$BASE/ready" >/dev/null && break; sleep 2; done
  check "room survives restart" "CI room" -b "$JAR" "$BASE/api/rooms"
fi

if [ $FAILED -ne 0 ] && [ -n "${GITHUB_ACTIONS:-}" ]; then
  annotate "compose logs" "$(docker compose ps 2>&1; docker compose logs --no-color --tail 60 2>&1 | tail -c 5500)"
fi
rm -f "$JAR"
exit $FAILED
