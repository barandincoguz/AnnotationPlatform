import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LockedOutScreen } from './LockedOutScreen'

describe('LockedOutScreen', () => {
  it('renders explainer + admin email', () => {
    render(<LockedOutScreen onLogout={vi.fn()} onGoToHelp={vi.fn()} />)
    expect(screen.getByText(/maksimum deneme sayısına ulaşıldı/i)).toBeInTheDocument()
    expect(screen.getByText(/team@example\.com/i)).toBeInTheDocument()
  })

  it('Çıkış yap → onLogout', async () => {
    const user = userEvent.setup()
    const onLogout = vi.fn()
    render(<LockedOutScreen onLogout={onLogout} onGoToHelp={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /çıkış yap/i }))
    expect(onLogout).toHaveBeenCalledOnce()
  })

  it('Yardımı incele → onGoToHelp', async () => {
    const user = userEvent.setup()
    const onGoToHelp = vi.fn()
    render(<LockedOutScreen onLogout={vi.fn()} onGoToHelp={onGoToHelp} />)
    await user.click(screen.getByRole('button', { name: /yardımı incele/i }))
    expect(onGoToHelp).toHaveBeenCalledOnce()
  })
})
