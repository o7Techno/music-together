import { tmpdir } from 'node:os'
import { join, sep } from 'node:path'

import { defineConfig, devices } from '@playwright/test'

// E2E поднимает собственные бэкенд (FakeProvider, SQLite во временном каталоге) и фронт на
// отдельных портах, чтобы не мешать `npm run dev`.
const API_PORT = Number(process.env.E2E_API_PORT ?? 8011)
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5181)
const origin = `http://localhost:${String(WEB_PORT)}`
// Флаг только для Chromium: WebKit на Linux падает на незнакомых аргументах.
const CHROMIUM_AUTOPLAY = '--autoplay-policy=no-user-gesture-required'
const dbFile = join(tmpdir(), `music-together-e2e-${String(Date.now())}.db`)
  .split(sep)
  .join('/')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: origin,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], launchOptions: { args: [CHROMIUM_AUTOPLAY] } },
      testIgnore: /mobile\.spec/,
    },
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 7'], launchOptions: { args: [CHROMIUM_AUTOPLAY] } },
      testMatch: /mobile\.spec/,
    },
    { name: 'mobile-webkit', use: { ...devices['iPhone 13'] }, testMatch: /mobile\.spec/ },
  ],
  webServer: [
    {
      command: `uv run uvicorn app.main:app --host 127.0.0.1 --port ${String(API_PORT)}`,
      cwd: '../backend',
      url: `http://127.0.0.1:${String(API_PORT)}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ENV: 'test',
        MUSIC_PROVIDER: 'fake',
        DATABASE_URL: `sqlite+aiosqlite:///${dbFile}`,
        DB_AUTO_CREATE: 'true',
        PUBLIC_ORIGIN: origin,
        LOG_LEVEL: 'WARNING',
      },
    },
    {
      command: `npm run dev -- --port ${String(WEB_PORT)}`,
      url: origin,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { BACKEND_URL: `http://127.0.0.1:${String(API_PORT)}` },
    },
  ],
})
