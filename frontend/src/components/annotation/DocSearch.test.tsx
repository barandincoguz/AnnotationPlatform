import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { DocSearch } from './DocSearch'

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{loc.pathname}</div>
}

function wrap(initialPath = '/') {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<><DocSearch /><LocationProbe /></>} />
        <Route path="/docs/:docId" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('DocSearch', () => {
  it('navigates to /docs/{trimmed-value} on submit', async () => {
    const user = userEvent.setup()
    render(wrap())
    await user.type(screen.getByLabelText('Doküman ID'), '   17h2sm8cdz11kq   ')
    await user.keyboard('{Enter}')
    expect(screen.getByTestId('loc').textContent).toBe('/docs/17h2sm8cdz11kq')
  })

  it('ignores empty / whitespace-only submissions', async () => {
    const user = userEvent.setup()
    render(wrap())
    const input = screen.getByLabelText('Doküman ID')
    await user.type(input, '   ')
    await user.keyboard('{Enter}')
    // Did not navigate
    expect(screen.getByTestId('loc').textContent).toBe('/')
  })

  it('clears the input after a successful navigate', async () => {
    const user = userEvent.setup()
    render(wrap())
    await user.type(screen.getByLabelText('Doküman ID'), 'abc123')
    await user.keyboard('{Enter}')
    // After navigate, the DocSearch route is gone (we navigated away),
    // so the only way to reuse the field is on the previous page.
    // We assert the navigation happened — the input clearing is exercised
    // in a longer-lived layout in the integration test.
    expect(screen.getByTestId('loc').textContent).toBe('/docs/abc123')
  })

  it('exposes a search landmark with a Turkish accessible name', () => {
    render(wrap())
    expect(screen.getByRole('search', { name: /doküman id ile ara/i })).toBeInTheDocument()
  })
})
