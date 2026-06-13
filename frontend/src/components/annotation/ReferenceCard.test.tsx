import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReferenceCard } from './ReferenceCard'
import { makeReferenceItem } from '@/test/msw-handlers'
import { emptyReferenceItem } from '@/lib/validateReferences'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

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
        isExpanded={true}
        onExpand={vi.fn()}
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
        isExpanded={true}
        onExpand={vi.fn()}
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
        isExpanded={true}
        onExpand={vi.fn()}
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
        isExpanded={true}
        onExpand={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/^metinden alıntı$/i)).toBeDisabled()
    expect(screen.getByLabelText(/^kanun no$/i)).toBeDisabled()
  })

  describe('ReferenceCard blur auto-splitting and normalization', () => {
    it('splits complex madde value on blur and triggers onChange', () => {
      const onChange = vi.fn()

      function TestWrapper() {
        const [val, setVal] = useState<ReferenceItem>(emptyReferenceItem())
        return (
          <ReferenceCard
            index={0}
            value={val}
            onChange={(next) => {
              setVal(next)
              onChange(next)
            }}
            onRemove={() => undefined}
            disabled={false}
            isExpanded={true}
            onExpand={() => undefined}
          />
        )
      }

      render(<TestWrapper />)

      const maddeInput = screen.getByLabelText('Madde')
      fireEvent.change(maddeInput, { target: { value: '16/1-a' } })
      fireEvent.blur(maddeInput)

      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          madde: '16',
          fikra: '1',
          bent: 'a',
        }),
      )
    })

    it('shows a live split warning while typing parseable complex madde', async () => {
      const user = userEvent.setup()

      function TestWrapper() {
        const [val, setVal] = useState<ReferenceItem>(emptyReferenceItem())
        return (
          <ReferenceCard
            index={0}
            value={val}
            onChange={setVal}
            onRemove={() => undefined}
            disabled={false}
            isExpanded={true}
            onExpand={() => undefined}
          />
        )
      }

      render(<TestWrapper />)

      const maddeInput = screen.getByLabelText('Madde')
      await user.type(maddeInput, '17/5-a')

      expect(screen.getByText('Kaydedilirken Madde 17, Fıkra 5, Bent a olarak ayrılacak.')).toBeInTheDocument()
      expect(maddeInput).toHaveAccessibleDescription('Kaydedilirken Madde 17, Fıkra 5, Bent a olarak ayrılacak.')
    })

    it('keeps ambiguous madde unchanged after blur and keeps showing the error', async () => {
      const user = userEvent.setup()

      function TestWrapper() {
        const [val, setVal] = useState<ReferenceItem>(emptyReferenceItem())
        return (
          <ReferenceCard
            index={0}
            value={val}
            onChange={setVal}
            onRemove={() => undefined}
            disabled={false}
            isExpanded={true}
            onExpand={() => undefined}
          />
        )
      }

      render(<TestWrapper />)

      const maddeInput = screen.getByLabelText('Madde')
      await user.type(maddeInput, '17--a')
      fireEvent.blur(maddeInput)

      expect(maddeInput).toHaveValue('17--a')
      expect(maddeInput).toHaveAttribute('aria-invalid', 'true')
      expect(screen.getByText('Madde formatı belirsiz. Örn: 17/5-a.')).toBeInTheDocument()
    })

    it('shows a bent cleanup warning and normalizes bent on blur', async () => {
      const user = userEvent.setup()

      function TestWrapper() {
        const [val, setVal] = useState<ReferenceItem>(emptyReferenceItem())
        return (
          <ReferenceCard
            index={0}
            value={val}
            onChange={setVal}
            onRemove={() => undefined}
            disabled={false}
            isExpanded={true}
            onExpand={() => undefined}
          />
        )
      }

      render(<TestWrapper />)

      const bentInput = screen.getByLabelText('Bent')
      await user.type(bentInput, '(A)')
      expect(screen.getByText('Kaydedilirken a olarak düzeltilecek.')).toBeInTheDocument()

      fireEvent.blur(bentInput)
      expect(bentInput).toHaveValue('a')
    })

    it('expands abbreviation for kanun_ad on blur', () => {
      const onChange = vi.fn()

      function TestWrapper() {
        const [val, setVal] = useState<ReferenceItem>(emptyReferenceItem())
        return (
          <ReferenceCard
            index={0}
            value={val}
            onChange={(next) => {
              setVal(next)
              onChange(next)
            }}
            onRemove={() => undefined}
            disabled={false}
            isExpanded={true}
            onExpand={() => undefined}
          />
        )
      }

      render(<TestWrapper />)

      const kanunAdInput = screen.getByLabelText('Kanun Adı')
      fireEvent.change(kanunAdInput, { target: { value: 'KVK' } })
      fireEvent.blur(kanunAdInput)

      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          kanun_ad: 'Kurumlar Vergisi Kanunu',
        }),
      )
    })

    it('preserves existing fikra and bent when entering a plain madde on blur', () => {
      const onChange = vi.fn()
      const initialItem = {
        ...emptyReferenceItem(),
        fikra: '2',
        bent: 'b',
      }

      function TestWrapper() {
        const [val, setVal] = useState<ReferenceItem>(initialItem)
        return (
          <ReferenceCard
            index={0}
            value={val}
            onChange={(next) => {
              setVal(next)
              onChange(next)
            }}
            onRemove={() => undefined}
            disabled={false}
            isExpanded={true}
            onExpand={() => undefined}
          />
        )
      }

      render(<TestWrapper />)

      const maddeInput = screen.getByLabelText('Madde')
      fireEvent.change(maddeInput, { target: { value: '16' } })
      fireEvent.blur(maddeInput)

      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          madde: '16',
          fikra: '2',
          bent: 'b',
        }),
      )
    })
  })
})
