import { expect, test } from '@playwright/test'

import { createRoom, newUser } from './helpers'

test('login, create a room and see it in "My rooms"', async ({ browser }) => {
  const page = await newUser(browser, 'Аня')
  const slug = await createRoom(page)
  expect(slug).toMatch(/^[a-z2-9]{5}-[a-z2-9]{5}$/)
  await expect(page.getByRole('heading', { name: 'Комната Аня' })).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('link', { name: /Комната Аня/ })).toBeVisible()
})

test('invite link asks a new user to log in, then enters the room', async ({ browser }) => {
  const anna = await newUser(browser, 'Аня')
  const slug = await createRoom(anna)
  const guest = await (await browser.newContext()).newPage()
  await guest.goto(`/r/${slug}`)
  await expect(guest.getByText('Вас пригласили послушать музыку вместе')).toBeVisible()
  await guest.getByPlaceholder('Например, Аня').fill('Гость')
  await guest.getByRole('button', { name: 'Войти' }).click()
  await expect(guest.getByRole('heading', { name: 'Комната Аня' })).toBeVisible()
  await expect(anna.getByTestId('members')).toContainText('Гость')
})
