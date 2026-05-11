import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { LoadingScreen } from './LoadingScreen'

describe('LoadingScreen', () => {
  it('shows spinner + "Yükleniyor..." in default (loading) mode', () => {
    renderWithProviders(<LoadingScreen />)
    expect(screen.getByText('Yükleniyor…')).toBeInTheDocument()
  })

  it('shows error message + Retry + Çıkış buttons in error mode', () => {
    renderWithProviders(<LoadingScreen mode="error" onRetry={vi.fn()} />)
    expect(screen.getByText(/Sunucuya bağlanılamadı/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tekrar dene/i })).toBeInTheDocument()
  })

  it('calls onRetry when the Retry button is clicked', () => {
    const onRetry = vi.fn()
    renderWithProviders(<LoadingScreen mode="error" onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: /Tekrar dene/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
