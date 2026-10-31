// Мобильная раскладка (эмуляция телефона): мини-плеер снизу, вкладки «Очередь / Добавить / Люди / Чат».

import { expect, test } from '@playwright/test'

test('mobile room: bottom tabs, mini player, full player sheet', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder('Например, Аня').fill('Телефон')
  await page.getByRole('button', { name: 'Войти' }).click()
  await page.getByRole('button', { name: 'Создать комнату' }).click()
  await page.waitForURL(/\/r\//)
  await expect(page.getByTestId('mini-player')).toBeVisible()
  // В пустой комнате плашки о звуке нет, а любое нажатие включает его.
  await expect(page.getByTestId('unlock')).toBeHidden()
  await page.getByTestId('mini-player').getByText('Ничего не играет').click()
  await expect
    .poll(() => page.evaluate(() => window.__roomSession?.engine.audioUnlocked))
    .toBe(true)
  await page.getByRole('button', { name: 'Свернуть плеер' }).tap()

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
  for (const tab of ['Очередь', 'Добавить', 'Люди', 'Чат']) {
    await nav.getByRole('button', { name: tab }).click()
    const report = await page.evaluate(() => {
      const width = document.documentElement.clientWidth
      const offenders = [...document.querySelectorAll<HTMLElement>('body *')]
        .filter((el) => el.offsetParent !== null && el.getBoundingClientRect().right > width + 1)
        .slice(0, 5)
        .map((el) => {
          const r = el.getBoundingClientRect()
          const cls = typeof el.className === 'string' ? el.className.slice(0, 80) : ''
          return `${el.tagName.toLowerCase()}.${cls} right=${String(Math.round(r.right))} w=${String(Math.round(r.width))}`
        })
      return {
        overflow: document.documentElement.scrollWidth - width,
        offenders,
      }
    })
    expect(report.overflow, `${tab}: ${report.offenders.join(' | ')}`).toBeLessThanOrEqual(0)
  }
})
