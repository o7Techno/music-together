// E2E волны на FakeProvider (SPEC-wave §10): треки подряд без ручного добавления, приоритет ручной
// очереди, пропуск, замена и остановка.

import { type Browser, type Page, expect, test } from '@playwright/test'

import { addTrack, createRoom, enterRoom, newUser, probe, waitPlaying } from './helpers'

async function pair(browser: Browser): Promise<[Page, Page]> {
  const anna = await newUser(browser, 'Аня')
  const slug = await createRoom(anna)
  const petya = await newUser(browser, 'Петя')
  await enterRoom(anna, slug)
  await enterRoom(petya, slug)
  return [anna, petya]
}

async function startWave(page: Page): Promise<void> {
  await page.getByRole('tab', { name: 'Волна' }).click()
  await page.getByRole('button', { name: /Включить мою волну/ }).click()
}

async function currentWaveTrack(page: Page): Promise<string> {
  await expect
    .poll(async () => (await probe(page))?.trackId ?? '', { timeout: 15_000 })
    .toMatch(/^fake-wave-/)
  return (await probe(page))?.trackId ?? ''
}

/** Перемотать почти в конец, чтобы не ждать трек целиком. */
async function seekNearEnd(page: Page, leftMs: number): Promise<void> {
  await page.evaluate((left) => {
    const session = window.__roomSession
    const state = session?.engine.state
    if (!session || !state) throw new Error('no session')
    void session.command({
      type: 'cmd.seek',
      positionMs: state.durationMs - left,
      expectedQueueItemId: state.queueItemId,
    })
  }, leftMs)
}

test('wave plays tracks in a row without adding anything', async ({ browser }) => {
  const [anna, petya] = await pair(browser)
  await startWave(anna)

  const first = await currentWaveTrack(petya)
  await waitPlaying(anna, first)
  await waitPlaying(petya, first)
  await expect(petya.getByTestId('track-source')).toHaveText('Моя волна · Аня')
  await expect(petya.getByTestId('events')).toContainText('включил(а) свою волну')
  await expect(petya.getByTestId('wave-next').getByRole('listitem').first()).toBeVisible()

  await seekNearEnd(petya, 1_500)
  await expect.poll(async () => (await probe(anna))?.trackId, { timeout: 15_000 }).not.toBe(first)
  const second = (await probe(anna))?.trackId ?? ''
  expect(second).toMatch(/^fake-wave-/)
  await waitPlaying(anna, second)
  await waitPlaying(petya, second)
})

test('manual track goes before the wave and the wave continues after it', async ({ browser }) => {
  const [anna, petya] = await pair(browser)
  await startWave(anna)
  const first = await currentWaveTrack(anna)
  await waitPlaying(anna, first)

  await petya.getByRole('tab', { name: 'Поиск' }).click()
  await addTrack(petya, 'короткий', 'Короткий')
  await expect(anna.getByTestId('queue')).toContainText('Короткий')

  await anna.getByRole('button', { name: 'Следующий', exact: true }).click()
  await waitPlaying(anna, 'fake-10')
  await expect(anna.getByTestId('track-source')).toHaveText('Добавил(а) Петя')

  await anna.getByRole('button', { name: 'Следующий', exact: true }).click()
  const after = await currentWaveTrack(anna)
  expect(after).not.toBe(first)
})

test('dislike skips the wave track; pin and remove change what is next', async ({ browser }) => {
  const [anna, petya] = await pair(browser)
  await startWave(anna)
  const first = await currentWaveTrack(anna)
  await waitPlaying(petya, first)

  await petya.getByRole('button', { name: 'Не нравится', exact: true }).click()
  await expect.poll(async () => (await probe(anna))?.trackId, { timeout: 10_000 }).not.toBe(first)

  const next = anna.getByTestId('wave-next').getByRole('listitem')
  const title = (await next.first().locator('p').first().textContent()) ?? ''
  await next.first().hover()
  await anna.getByRole('button', { name: `Закрепить «${title}» в очереди` }).click()
  await expect(anna.getByTestId('queue')).toContainText(title)
  await expect(anna.getByTestId('wave-next')).not.toContainText(title)

  const other = (await next.first().locator('p').first().textContent()) ?? ''
  await next.first().hover()
  await anna.getByRole('button', { name: `Убрать «${other}» из волны` }).click()
  await expect(anna.getByTestId('wave-next')).not.toContainText(other)
})

test('another member replaces the wave after confirming, anyone can stop it', async ({
  browser,
}) => {
  const [anna, petya] = await pair(browser)
  await startWave(anna)
  await currentWaveTrack(petya)

  petya.once('dialog', (d) => {
    expect(d.message()).toContain('Заменить волну Аня')
    void d.accept()
  })
  await petya.getByRole('tab', { name: 'Волна' }).click()
  await petya.getByRole('button', { name: /Включить мою волну/ }).click()
  await expect(anna.getByTestId('events')).toContainText('заменил(а) волну на свою')
  await anna.getByRole('tab', { name: 'Волна' }).click()
  await expect(anna.getByTestId('wave-status')).toContainText('Моя волна · Петя')

  await anna.getByRole('button', { name: 'Остановить волну' }).click()
  await expect(petya.getByTestId('events')).toContainText('остановил(а) волну')
  await expect(petya.getByTestId('wave-next')).toBeHidden()
})

test('wave by seed shows what it is based on', async ({ browser }) => {
  const [anna] = await pair(browser)
  await anna.getByRole('tab', { name: 'Волна' }).click()
  await anna.getByRole('combobox', { name: 'Волна: Занятие' }).selectOption({ label: 'Спорт' })
  await currentWaveTrack(anna)
  await expect(anna.getByTestId('track-source')).toHaveText('Волна по: Спорт')
  await expect(anna.getByTestId('wave-status')).toContainText('Волна по: Спорт')
})

test('repeat button skips queue mode while the wave is on', async ({ browser }) => {
  const [anna] = await pair(browser)
  await startWave(anna)
  await currentWaveTrack(anna)
  await anna.getByRole('button', { name: 'Повтор выключен' }).click()
  await expect(anna.getByRole('button', { name: 'Повтор трека' })).toBeVisible()
})
