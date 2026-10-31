// E2E фазы 4: чат и реакции, права создателя, горячие клавиши, Media Session, темы.

import { type Page, expect, test } from '@playwright/test'

import { addTrack, createRoom, enterRoom, newUser, probe, waitPlaying } from './helpers'

async function pair(browser: import('@playwright/test').Browser): Promise<[Page, Page, string]> {
  const anna = await newUser(browser, 'Аня')
  const slug = await createRoom(anna)
  const petya = await newUser(browser, 'Петя')
  await enterRoom(anna, slug)
  await enterRoom(petya, slug)
  return [anna, petya, slug]
}

test('chat messages and track reactions reach everyone', async ({ browser }) => {
  const [anna, petya] = await pair(browser)
  await addTrack(anna, 'минута', 'Минута ровно')
  await waitPlaying(anna, 'fake-3')

  await anna.getByRole('tab', { name: /Чат/ }).click()
  await anna.getByLabel('Сообщение в чат').fill('Привет! Огонь трек')
  await anna.getByRole('button', { name: 'Отправить' }).click()
  await petya.getByRole('tab', { name: /Чат/ }).click()
  await expect(petya.getByTestId('chat')).toContainText('Привет! Огонь трек')

  await petya.getByRole('button', { name: 'Реакция 🔥' }).click()
  await expect(anna.getByTestId('chat')).toContainText('Петя реагирует на трек')
})

test('owner can rename, kick, reissue the link and delete the room', async ({ browser }) => {
  const [anna, petya, slug] = await pair(browser)
  // Не создатель не видит настроек.
  await expect(petya.getByRole('button', { name: 'Настройки комнаты' })).toHaveCount(0)

  await anna.getByRole('button', { name: 'Настройки комнаты' }).click()
  const dialog = anna.getByRole('dialog', { name: 'Настройки комнаты' })
  await dialog.getByLabel('Название').fill('Пятничный вечер')
  await dialog.getByRole('button', { name: 'Сохранить' }).click()
  await expect(petya.getByRole('heading', { name: 'Пятничный вечер' })).toBeVisible()
  await expect(petya.getByTestId('events')).toContainText('переименовал(а) комнату')

  // Перевыпуск ссылки: старая не работает, подключённые остаются.
  await dialog.getByRole('button', { name: 'Перевыпустить ссылку' }).click()
  await expect(anna).not.toHaveURL(new RegExp(`/r/${slug}$`))
  const guest = await newUser(browser, 'Гость')
  await guest.goto(`/r/${slug}`)
  await expect(guest.getByText(/Комната не найдена/)).toBeVisible()

  // Выгнать Петю.
  anna.once('dialog', (d) => void d.accept())
  await anna.getByRole('button', { name: 'Убрать Петя из комнаты' }).click()
  await expect(petya.getByText('Создатель комнаты закрыл вам доступ.')).toBeVisible()

  // Удалить комнату.
  await anna.getByRole('button', { name: 'Настройки комнаты' }).click()
  await anna.getByRole('button', { name: 'Удалить комнату' }).click()
  await anna.getByRole('button', { name: 'Да, удалить' }).click()
  await expect(anna).toHaveURL(/\/$/)
})

test('hotkeys and Media Session control the room', async ({ browser }) => {
  const [anna, petya] = await pair(browser)
  await addTrack(anna, 'четыре', 'Четыре минуты')
  await waitPlaying(anna, 'fake-9')

  await anna.locator('body').click({ position: { x: 5, y: 5 } })
  await anna.keyboard.press('Space')
  await expect.poll(async () => (await probe(petya))?.status).toBe('paused')
  await anna.keyboard.press('Space')
  await waitPlaying(petya, 'fake-9')

  const before = (await probe(petya))?.expectedMs ?? 0
  await anna.keyboard.press('ArrowRight')
  await expect
    .poll(async () => ((await probe(petya))?.expectedMs ?? 0) - before, { timeout: 5000 })
    .toBeGreaterThan(8_000)

  const title = await anna.evaluate(() => navigator.mediaSession.metadata?.title)
  expect(title).toBe('Четыре минуты')
  const artist = await anna.evaluate(() => navigator.mediaSession.metadata?.artist)
  expect(artist).toBe('Щелчки и Ко')
})

test('theme toggle switches to light and is remembered', async ({ browser }) => {
  const page = await newUser(browser, 'Аня')
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.getByRole('button', { name: /Тема: тёмная/ }).click()
  await expect(page.locator('html')).toHaveClass(/light/)
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/light/)
})

test('player controls stay inside the player column', async ({ browser }) => {
  const page = await newUser(browser, 'Аня')
  const slug = await createRoom(page)
  await enterRoom(page, slug)
  for (const width of [1024, 1280, 1920]) {
    await page.setViewportSize({ width, height: 800 })
    const player = await page.getByRole('region', { name: 'Плеер', exact: true }).boundingBox()
    const volume = await page.getByRole('slider', { name: 'Громкость' }).boundingBox()
    if (!player || !volume) throw new Error('no boxes')
    expect(volume.x + volume.width, `ширина окна ${String(width)}`).toBeLessThanOrEqual(
      player.x + player.width,
    )
  }
})
