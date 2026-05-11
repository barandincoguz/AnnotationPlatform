import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { ErrorBoundary } from './ErrorBoundary'
import { silenceConsoleError } from '@/test/setup'

function Bomb(): never {
  throw new Error('boom from Bomb')
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    renderWithProviders(
      <ErrorBoundary>
        <div data-testid="child">ok</div>
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('renders fallback when a child throws', () => {
    silenceConsoleError() // React always console.errors caught errors
    renderWithProviders(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/bir şeyler ters gitti/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sayfayı yenile/i })).toBeInTheDocument()
  })
})
