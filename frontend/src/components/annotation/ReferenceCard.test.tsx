import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReferenceCard } from './ReferenceCard'
import { makeReferenceItem } from '@/test/msw-handlers'

describe('ReferenceCard', () => {
  it('renders all 6 fields with their current values', () => {
    render(
      <ReferenceCard
        index={0}
        value={makeReferenceItem({
          kanun_no: '213',
          kanun_ad: 'VUK',
          madde: '359',
          fikra: 'b',
          bent: '1',
          source_text: 'quote',
        })}
        onChange={vi.fn()}
        onRemove={vi.fn()}
        disabled={false}
      />,
    )
    expect(screen.getByLabelText(/^kanun no$/i)).toHaveValue('213')
    expect(screen.getByLabelText(/^madde$/i)).toHaveValue('359')
    expect(screen.getByLabelText(/^metinden alıntı$/i)).toHaveValue('quote')
  })

  it('calls onChange on input edits', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <ReferenceCard
        index={0}
        value={makeReferenceItem({ madde: '' })}
        onChange={onChange}
        onRemove={vi.fn()}
        disabled={false}
      />,
    )
    await user.type(screen.getByLabelText(/^madde$/i), '5')
    expect(onChange).toHaveBeenCalled()
  })

  it('calls onRemove when delete button is clicked', () => {
    const onRemove = vi.fn()
    render(
      <ReferenceCard
        index={0}
        value={makeReferenceItem()}
        onChange={vi.fn()}
        onRemove={onRemove}
        disabled={false}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /sil/i }))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })

  it('disables all inputs when disabled=true', () => {
    render(
      <ReferenceCard
        index={0}
        value={makeReferenceItem()}
        onChange={vi.fn()}
        onRemove={vi.fn()}
        disabled={true}
      />,
    )
    expect(screen.getByLabelText(/^metinden alıntı$/i)).toBeDisabled()
    expect(screen.getByLabelText(/^kanun no$/i)).toBeDisabled()
  })
})
