// E2E добавления треков и работы с очередью (SPEC §3.3–3.5, §3.7) на FakeProvider.
// FakeProvider понимает настоящие ссылки Яндекса с маленькими id: /album/1/track/3 → «Минута ровно».

import { type Page, expect, test } from '@playwright/test'

import { createRoom, enterRoom, newUser, waitPlaying } from './helpers'

async function room(browser: import('@playwright/test').Browser): Promise<Page> {
  const page = await newUser(browser, 'Аня')
  const slug = await createRoom(page)
  await enterRoom(page, slug)
  return page
}

const queueTitles = (page: Page) => page.getByTestId('queue').getByRole('listitem')

async function pasteAnywhere(page: Page, text: string): Promise<void> {
  await page.locator('body').click({ position: { x: 5, y: 5 } })
  await page.evaluate((t) => {
    const dt = new DataTransfer()
    dt.setData('text/plain', t)
    document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true }))
  }, text)
}

test('search with keyboard: Enter adds, Shift+Enter plays next, "/" focuses search', async ({
  browser,
}) => {
  const page = await room(browser)
  await page.locator('body').click({ position: { x: 5, y: 5 } })
  await page.keyboard.press('/')
  await expect(page.locator('[data-search-input]')).toBeFocused()

  await page.keyboard.type('минута')
  await expect(page.getByTestId('search-results').getByRole('option').first()).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('track-title')).toHaveText('Минута ровно')

  await page.locator('[data-search-input]').fill('метроном')
  await expect(page.getByRole('option', { name: /Тридцать щелчков/ })).toBeVisible()
  await page.keyboard.press('Enter') // первый трек исполнителя — в конец
  await page.locator('[data-search-input]').fill('короткий')
  await expect(page.getByRole('option', { name: /Короткий/ })).toBeVisible()
  await page.keyboard.press('Shift+Enter') // играть следующим
  await expect(queueTitles(page).first()).toContainText('Короткий')
})

test('Ctrl+V of a share link anywhere shows "Add?" and adds the track', async ({ browser }) => {
  const page = await room(browser)
  await pasteAnywhere(
    page,
    'Послушай: https://music.yandex.ru/album/1/track/3?ref_id=ABC&utm_medium=copy_link',
  )
  const dialog = page.getByTestId('paste-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByTestId('link-card')).toContainText('Минута ровно')
  await dialog.getByRole('button', { name: 'В очередь' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByTestId('track-title')).toHaveText('Минута ровно')

  // Несколько ссылок за раз, по одной на строку, во вкладке «По ссылке».
  await page.getByRole('tab', { name: 'По ссылке' }).click()
  await page
    .getByTestId('link-input')
    .fill('https://music.yandex.ru/album/1/track/10\nhttps://music.yandex.ru/album/2')
  await page.getByRole('button', { name: 'Найти 2 ссылки' }).click()
  const tab = page.getByTestId('link-tab')
  await expect(tab.getByTestId('link-card')).toHaveCount(2)
  await tab.getByRole('button', { name: /Добавить всё/ }).click()
  await expect(queueTitles(page)).toHaveCount(4) // 1 трек + 3 трека альбома «Частоты»
})

test('playlist from "My playlists": select some tracks and add them', async ({ browser }) => {
  const page = await room(browser)
  await page.getByRole('tab', { name: 'Мои плейлисты' }).click()
  await page.getByRole('button', { name: /Короткие/ }).click()
  const view = page.getByTestId('entity-view')
  await expect(view.getByTestId('entity-tracks').getByRole('listitem')).toHaveCount(3)
  await view.getByLabel('Выбрать «Сорок пять»').check()
  await view.getByLabel('Выбрать «Короткий»').check()
  await view.getByRole('button', { name: 'Добавить 2' }).click()
  // Первый добавленный сразу заиграл, второй — в очереди.
  await expect(page.getByTestId('track-title')).toHaveText('Короткий')
  await expect(queueTitles(page)).toHaveCount(1)
  await expect(page.getByTestId('events')).toContainText(
    'добавил(а) 2 трека из плейлиста «Короткие»',
  )

  // «Мне нравится» → «Все вперемешку».
  await view.getByRole('button', { name: 'Назад' }).click()
  await page.getByRole('button', { name: /Мне нравится/ }).click()
  await page.getByRole('button', { name: 'Все вперемешку' }).click()
  await expect(queueTitles(page)).toHaveCount(4)
})

test('duplicates are confirmed, not blocked', async ({ browser }) => {
  const page = await room(browser)
  await page.locator('[data-search-input]').fill('минута')
  await page.getByRole('button', { name: 'Добавить «Минута ровно» в очередь' }).click()
  await expect(page.getByTestId('track-title')).toHaveText('Минута ровно')
  await page.getByRole('button', { name: 'Добавить «Минута ровно» в очередь' }).click()
  await expect(page.getByText('Этот трек уже в очереди. Добавить ещё раз?')).toBeVisible()
  await page.getByRole('button', { name: 'Добавить', exact: true }).click()
  await expect(queueTitles(page)).toHaveCount(1)
})

test('queue: remove with undo, drag to reorder, clear with confirmation, history', async ({
  browser,
}) => {
  const page = await room(browser)
  await page.getByRole('tab', { name: 'Мои плейлисты' }).click()
  await page.getByRole('button', { name: /Все тестовые треки/ }).click()
  await page.getByRole('button', { name: 'Добавить все' }).click()
  await waitPlaying(page, 'fake-1')
  await expect(queueTitles(page)).toHaveCount(9)

  // Удаление с «Отменить»
  await page.getByRole('button', { name: 'Убрать «Сорок пять» из очереди' }).click()
  await expect(queueTitles(page)).toHaveCount(8)
  await page.getByRole('button', { name: 'Отменить' }).click()
  await expect(queueTitles(page)).toHaveCount(9)
  await expect(queueTitles(page).first()).toContainText('Сорок пять')

  // Перетаскивание: третий трек — наверх.
  const handle = page.getByRole('button', { name: 'Перетащить «Семьдесят пять»' })
  const target = page.getByRole('button', { name: 'Перетащить «Сорок пять»' })
  const from = await handle.boundingBox()
  const to = await target.boundingBox()
  if (!from || !to) throw new Error('no boxes')
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + from.width / 2, from.y - 10, { steps: 5 })
  await page.mouse.move(to.x + to.width / 2, to.y + 2, { steps: 15 })
  await page.mouse.up()
  await expect(queueTitles(page).first()).toContainText('Семьдесят пять')

  // «Следующий» → первый трек уходит в историю; возвращаем его в очередь.
  await page.getByRole('button', { name: 'Следующий', exact: true }).click()
  await waitPlaying(page, 'fake-4')
  await page.getByRole('button', { name: /История/ }).click()
  await expect(page.getByTestId('history')).toContainText('Тридцать щелчков')
  await page.getByRole('button', { name: 'Вернуть «Тридцать щелчков» в очередь' }).click()
  await page.getByRole('button', { name: 'Показать очередь' }).click()
  await expect(queueTitles(page).last()).toContainText('Тридцать щелчков')

  // Очистка — только после подтверждения.
  await page.getByRole('button', { name: 'Очистить очередь' }).click()
  await page.getByRole('button', { name: 'Отмена' }).click()
  await expect(queueTitles(page)).not.toHaveCount(0)
  await page.getByRole('button', { name: 'Очистить очередь' }).click()
  await page.getByRole('button', { name: 'Очистить', exact: true }).click()
  await expect(page.getByText('Найдите трек или вставьте ссылку')).toBeVisible()
})
