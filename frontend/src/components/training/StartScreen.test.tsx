import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StartScreen } from './StartScreen'

describe('StartScreen', () => {
  it('renders warning copy', () => {
    render(<StartScreen onStart={vi.fn()} onBackToHelp={vi.fn()} isPending={false} />)
    expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument()
  })

  it('Başla disabled until checkbox checked', async () => {
    const user = userEvent.setup()
    render(<StartScreen onStart={vi.fn()} onBackToHelp={vi.fn()} isPending={false} />)
    expect(screen.getByRole('button', { name: /^başla$/i })).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: /^başla$/i })).not.toBeDisabled()
  })

  it('Başla click triggers onStart', async () => {
    const user = userEvent.setup()
    const onStart = vi.fn()
    render(<StartScreen onStart={onStart} onBackToHelp={vi.fn()} isPending={false} />)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^başla$/i }))
    expect(onStart).toHaveBeenCalledOnce()
  })

  it('Başla disabled while pending', async () => {
    const user = userEvent.setup()
    render(<StartScreen onStart={vi.fn()} onBackToHelp={vi.fn()} isPending={true} />)
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: /başla|başlatılıyor/i })).toBeDisabled()
  })

  it('Kılavuza dön invokes onBackToHelp', async () => {
    const user = userEvent.setup()
    const onBack = vi.fn()
    render(<StartScreen onStart={vi.fn()} onBackToHelp={onBack} isPending={false} />)
    await user.click(screen.getByRole('button', { name: /kılavuza dön/i }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
