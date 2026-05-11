import { describe, it, expect } from 'vitest'
import { screen, render } from '@testing-library/react'
import { Route, Routes, MemoryRouter } from 'react-router-dom'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders an outlet so nested routes display below the header', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<div data-testid="child">child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})
