import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PendingStartBanner } from './PendingStartBanner'

describe('PendingStartBanner', () => {
  it('renders warning copy', () => {
    render(<PendingStartBanner onDismiss={vi.fn()} onStartNew={vi.fn()} />)
    expect(screen.getByText(/önceki başlatma yarıda kaldı/i)).toBeInTheDocument()
  })

  it('Anladım, kapat → onDismiss', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<PendingStartBanner onDismiss={onDismiss} onStartNew={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /anladım, kapat/i }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('Yeni denemeyi başlat → onStartNew', async () => {
    const user = userEvent.setup()
    const onStartNew = vi.fn()
    render(<PendingStartBanner onDismiss={vi.fn()} onStartNew={onStartNew} />)
    await user.click(screen.getByRole('button', { name: /yeni denemeyi başlat/i }))
    expect(onStartNew).toHaveBeenCalledOnce()
  })
})
