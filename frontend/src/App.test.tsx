import { render, screen } from '@testing-library/react'

import { App } from './App'

describe('App', () => {
  it('renders the product title', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Слушаем вместе' })).toBeInTheDocument()
  })
})
