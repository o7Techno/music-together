# DECISIONS — журнал решений и отступлений от ТЗ

Формат: **что решено** · почему · альтернативы. Отступления от `SPEC.md` помечены **[отступление]**.

---

## D-001. Таск-раннер — корневой `package.json` вместо `make`
- **Решение:** `npm run dev`, `npm run check` и т.д. в корневом `package.json` (+ `concurrently`).
- **Почему:** ТЗ допускает «`make dev` или аналог»; основная машина разработки — Windows без `make`.
  Node всё равно обязателен для фронта, npm-скрипты работают одинаково на Windows/Linux/macOS/CI.
- **Альтернативы:** Makefile (нет на Windows из коробки), `just` (ещё одна зависимость), `tasks.py`.

## D-002. TypeScript 6.0, а не 7
- **Решение:** `typescript@~6.0`.
- **Почему:** шаблон Vite ставит TS 7 (нативный порт), но `typescript-eslint` поддерживает TS < 6.1,
  а ТЗ требует ESLint. Шаблонный `oxlint` заменён на ESLint + Prettier по ТЗ.
- **Пересмотреть:** когда typescript-eslint объявит поддержку TS 7.

## D-003. React 19 (ТЗ: «React 18+»)
- Текущий стабильный, совместим со всеми библиотеками стека. Требованию «18+» удовлетворяет.

## D-004. `yandex-music[async,crypto]`
- **Решение:** extras `async` (aiohttp — без него `ClientAsync` не работает) и `crypto`.
- **Прокси:** библиотека пробрасывает `proxy_url` в aiohttp, который нативно умеет только HTTP(S)-прокси.
  Для `socks5://` понадобится `aiohttp-socks` — добавлю в фазе 2 вместе с `YM_PROXY_URL`.

## D-005. Device Flow — средствами библиотеки
- `yandex-music` 3.2.2 умеет OAuth Device Flow пошагово: `request_device_code()` и
  `poll_device_token()` (client_id/secret официального Android-приложения Яндекс Музыки).
  Это ложится ровно на `/api/auth/device/start` + `/api/auth/device/poll` без своей реализации протокола.
- Проверено без токена из NL: код из 8 символов, страница `https://ya.ru/device`, срок жизни кода 300 с,
  рекомендованный интервал опроса 5 с. Ответ содержит `refresh_token` → можно обновлять токен.

## D-006. Предупреждение Starlette про `httpx` в TestClient — отфильтровано
- Starlette предлагает сторонний пакет вместо `httpx`; ставить неизвестную зависимость ради теста
  не стал, предупреждение отфильтровано в `pytest` (`filterwarnings`).
