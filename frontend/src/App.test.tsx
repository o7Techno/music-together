import { render, screen } from '@testing-library/react'

import { App } from './App'

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          url.includes('/api/auth/config')
            ? Response.json({ devLogin: true, yandexLogin: false })
            : Response.json({ me: null }),
        ),
      ),
    )
  })

  it('shows the product title and the login form for anonymous users', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Слушаем вместе' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Войти' })).toBeInTheDocument()
  })
})
