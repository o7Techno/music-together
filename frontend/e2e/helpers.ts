import { type Browser, type Page, expect } from '@playwright/test'

import type { SyncProbe } from '../src/player/syncEngine'

export async function newUser(browser: Browser, name: string): Promise<Page> {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/')
  await page.getByPlaceholder('Например, Аня').fill(name)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByRole('heading', { name: 'Мои комнаты' })).toBeVisible()
  return page
}

export async function createRoom(page: Page): Promise<string> {
  await page.getByRole('button', { name: 'Создать комнату' }).click()
  await page.waitForURL(/\/r\/[a-z0-9-]+$/)
  const slug = new URL(page.url()).pathname.split('/').pop()
  if (!slug) throw new Error('no slug')
  return slug
}

export async function enterRoom(page: Page, slug: string): Promise<void> {
  if (!page.url().endsWith(`/r/${slug}`)) await page.goto(`/r/${slug}`)
  await page.getByTestId('unlock').click()
  await expect(page.getByTestId('unlock')).toBeHidden()
}

export async function addTrack(page: Page, query: string, title: string): Promise<void> {
  const input = page.locator('[data-search-input]')
  await input.fill(query)
  await page.getByRole('button', { name: `Добавить «${title}» в очередь` }).click()
}

export function probe(page: Page): Promise<SyncProbe | null> {
  return page.evaluate(() => window.__syncProbe?.() ?? null)
}

export async function waitPlaying(page: Page, trackId?: string, timeout = 15_000): Promise<void> {
  await expect
    .poll(
      async () => {
        const p = await probe(page)
        return (
          p?.status === 'playing' &&
          p.playing &&
          p.driftMs !== null &&
          (!trackId || p.trackId === trackId)
        )
      },
      { timeout, intervals: [100] },
    )
    .toBe(true)
}

export interface SpreadStats {
  samples: number
  spreadMedianMs: number
  spreadP95Ms: number
  spreadMaxMs: number
  absDriftMedianMs: number
  absDriftP95Ms: number
}

export function percentile(values: number[], q: number): number {
  const sorted = [...values].sort((a, b) => a - b)
  if (sorted.length === 0) return NaN
  const k = (sorted.length - 1) * q
  const lo = Math.floor(k)
  const hi = Math.min(lo + 1, sorted.length - 1)
  return (sorted[lo] ?? 0) + ((sorted[hi] ?? 0) - (sorted[lo] ?? 0)) * (k - lo)
}

/**
 * Собрать рассинхрон между клиентами. Все клиенты считают позицию по одной формуле сервера,
 * поэтому разница фактических позиций в один момент серверного времени = разница их drift.
 * На каждом шаге: spread = max(drift) − min(drift) по клиентам.
 */
export async function measureSpread(
  pages: Page[],
  durationMs: number,
  intervalMs = 250,
): Promise<SpreadStats> {
  const spreads: number[] = []
  const absDrifts: number[] = []
  const deadline = Date.now() + durationMs
  while (Date.now() < deadline) {
    const probes = await Promise.all(pages.map(probe))
    const drifts = probes.map((p) => p?.driftMs).filter((d): d is number => typeof d === 'number')
    if (drifts.length === pages.length) {
      spreads.push(Math.max(...drifts) - Math.min(...drifts))
      absDrifts.push(...drifts.map(Math.abs))
    }
    await pages[0]?.waitForTimeout(intervalMs)
  }
  return {
    samples: spreads.length,
    spreadMedianMs: percentile(spreads, 0.5),
    spreadP95Ms: percentile(spreads, 0.95),
    spreadMaxMs: Math.max(...spreads),
    absDriftMedianMs: percentile(absDrifts, 0.5),
    absDriftP95Ms: percentile(absDrifts, 0.95),
  }
}
