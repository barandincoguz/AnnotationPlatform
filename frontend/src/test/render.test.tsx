import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from './render'

describe('renderWithProviders', () => {
  it('renders the ui element at the initialEntries pathname', () => {
    renderWithProviders(<div data-testid="hello">hi</div>, { initialEntries: ['/'] })
    expect(screen.getByTestId('hello')).toBeInTheDocument()
  })

  it('exposes destination stubs at the default paths so Navigate side-effects are observable', () => {
    // Render an element at /login (one of the default stubs). The helper's
    // wrapping Routes tree should match /login → our element, and the
    // other default stubs (/, /register, /help, /training) remain accessible.
    renderWithProviders(<div data-testid="here">at-login</div>, { initialEntries: ['/login'] })
    expect(screen.getByTestId('here')).toBeInTheDocument()
  })
})
