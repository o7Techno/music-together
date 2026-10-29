// Мобильная раскладка (эмуляция телефона): мини-плеер снизу, вкладки «Очередь / Добавить / Люди / Чат».

import { expect, test } from '@playwright/test'

test('mobile room: bottom tabs, mini player, full player sheet', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder('Например, Аня').fill('Телефон')
  await page.getByRole('button', { name: 'Войти' }).click()
  await page.getByRole('button', { name: 'Создать комнату' }).click()
  await page.waitForURL(/\/r\//)
  await page.getByTestId('unlock').click()

  const nav = page.getByRole('navigation', { name: 'Разделы комнаты' })
  await expect(nav).toBeVisible()
  await expect(page.getByTestId('mini-player')).toContainText('Ничего не играет')

  await nav.getByRole('button', { name: 'Добавить' }).click()
  await page.locator('[data-search-input]').fill('минута')
  await page.getByRole('button', { name: 'Добавить «Минута ровно» в очередь' }).tap()
  await expect(page.getByTestId('mini-player')).toContainText('Минута ровно')

  await nav.getByRole('button', { name: 'Люди' }).click()
  await expect(page.getByTestId('members')).toContainText('Телефон')
  await nav.getByRole('button', { name: 'Чат' }).click()
  await expect(page.getByLabel('Сообщение в чат')).toBeVisible()

  await page.getByRole('button', { name: 'Открыть плеер' }).tap()
  const sheet = page.getByRole('dialog', { name: 'Плеер' })
  await expect(sheet.getByTestId('track-title')).toHaveText('Минута ровно')
  await sheet.getByRole('button', { name: 'Свернуть плеер' }).tap()
  await expect(sheet).toBeHidden()

  // Нет горизонтальной прокрутки на узком экране.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})
