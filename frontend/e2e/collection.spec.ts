// E2E лайков и плейлистов (SPEC-wave §6, §10): всё действует только на аккаунт того, кто нажал.

import { type Browser, type Page, expect, test } from '@playwright/test'

import { addTrack, createRoom, enterRoom, newUser, waitPlaying } from './helpers'

async function pairWithTrack(browser: Browser): Promise<[Page, Page]> {
  const anna = await newUser(browser, 'Аня')
  const slug = await createRoom(anna)
  const petya = await newUser(browser, 'Петя')
  await enterRoom(anna, slug)
  await enterRoom(petya, slug)
  await addTrack(anna, 'короткий', 'Короткий')
  await waitPlaying(anna, 'fake-10')
  await waitPlaying(petya, 'fake-10')
  return [anna, petya]
}

test('like is personal, shows in the feed and on the current track', async ({ browser }) => {
  const [anna, petya] = await pairWithTrack(browser)
  const player = (p: Page) => p.getByRole('region', { name: 'Плеер', exact: true })

  await player(anna).getByRole('button', { name: 'Лайкнуть «Короткий»' }).click()
  await expect(player(anna).getByRole('button', { name: /Убрать «Короткий»/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(petya.getByTestId('events')).toContainText('лайкнул(а) «Короткий»')
  await expect(petya.getByTestId('track-likers')).toHaveText('1')
  // У Пети ♥ своё: он ничего не лайкал.
  await expect(player(petya).getByRole('button', { name: 'Лайкнуть «Короткий»' })).toHaveAttribute(
    'aria-pressed',
    'false',
  )

  await player(anna)
    .getByRole('button', { name: /Убрать «Короткий»/ })
    .click()
  await expect(player(anna).getByRole('button', { name: 'Лайкнуть «Короткий»' })).toBeVisible()
  await expect(petya.getByTestId('track-likers')).toBeHidden()
})

test('L likes the current track, even in the Russian layout', async ({ browser }) => {
  const [anna] = await pairWithTrack(browser)
  await anna.locator('body').click({ position: { x: 5, y: 5 } })
  await anna.keyboard.press('KeyL')
  await expect(
    anna
      .getByRole('region', { name: 'Плеер', exact: true })
      .getByRole('button', { name: /Убрать «Короткий»/ }),
  ).toBeVisible()
})

test('add to a new playlist from the player and from the queue, duplicate asks', async ({
  browser,
}) => {
  const [anna, petya] = await pairWithTrack(browser)
  await anna
    .getByRole('region', { name: 'Плеер', exact: true })
    .getByRole('button', { name: 'Добавить «Короткий» в плейлист' })
    .click()
  const dialog = anna.getByRole('dialog', { name: 'Добавить в плейлист' })
  await dialog.getByLabel('Название нового плейлиста').fill('Для дороги')
  await dialog.getByRole('button', { name: 'Создать' }).click()
  await expect(anna.getByText('Добавлено в «Для дороги»')).toBeVisible()
  await expect(dialog).toBeHidden()

  // Трек из очереди — в тот же плейлист.
  await addTrack(anna, 'минута', 'Минута ровно')
  const row = anna.getByTestId('queue').getByRole('listitem').first()
  await row.hover()
  await row.getByRole('button', { name: 'Добавить «Минута ровно» в плейлист' }).click()
  await dialog.getByRole('button', { name: /Для дороги/ }).click()
  await expect(anna.getByText('Добавлено в «Для дороги»').last()).toBeVisible()
  await expect(dialog).toBeHidden()

  // Повторно тот же трек: вопрос, а не молчаливый дубль.
  await anna
    .getByRole('region', { name: 'Плеер', exact: true })
    .getByRole('button', { name: 'Добавить «Короткий» в плейлист' })
    .click()
  await dialog.getByRole('button', { name: /Для дороги/ }).click()
  await expect(dialog.getByText('Этот трек уже есть в «Для дороги».')).toBeVisible()
  await dialog.getByRole('button', { name: 'Отмена' }).click()
  await dialog.getByRole('button', { name: 'Закрыть' }).click()

  // У Пети этого плейлиста нет.
  await petya
    .getByRole('region', { name: 'Плеер', exact: true })
    .getByRole('button', { name: 'Добавить «Короткий» в плейлист' })
    .click()
  const his = petya.getByRole('dialog', { name: 'Добавить в плейлист' })
  await expect(his.getByText('Своих плейлистов пока нет')).toBeVisible()
})

test('whole queue can be saved to a playlist', async ({ browser }) => {
  const [anna] = await pairWithTrack(browser)
  await addTrack(anna, 'минута', 'Минута ровно')
  await addTrack(anna, 'сорок', 'Сорок пять')
  await anna.getByRole('button', { name: 'Сохранить очередь в плейлист' }).click()
  const dialog = anna.getByRole('dialog', { name: 'Добавить в плейлист' })
  await dialog.getByLabel('Название нового плейлиста').fill('Вечер')
  await dialog.getByRole('button', { name: 'Создать' }).click()
  await expect(anna.getByText('Добавлено в «Вечер»')).toBeVisible()
  await anna.getByRole('tab', { name: 'Мои плейлисты' }).click()
  await expect(anna.getByRole('button', { name: /Вечер/ })).toBeVisible()
})
