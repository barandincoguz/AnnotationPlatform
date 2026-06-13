import { useState } from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConceptRowEditor } from './ConceptRowEditor'
import type { Concept } from '@/lib/adminSchemas'

const baseConcept: Concept = {
  kanun_no: '5520',
  kanun_ad: null,
  madde: null,
  fikra: null,
  bent: null,
}

function TestWrapper({ initial = baseConcept }: { initial?: Concept }) {
  const [value, setValue] = useState<Concept>(initial)
  return (
    <ConceptRowEditor
      value={value}
      onChange={setValue}
      onRemove={() => undefined}
    />
  )
}

describe('ConceptRowEditor', () => {
  it('shows a live madde split warning and splits parseable madde on blur', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    const maddeInput = screen.getByLabelText('madde')
    await user.type(maddeInput, '17/5-a')

    expect(screen.getByText('Kaydedilirken Madde 17, Fıkra 5, Bent a olarak ayrılacak.')).toBeInTheDocument()

    fireEvent.blur(maddeInput)

    expect(maddeInput).toHaveValue('17')
    expect(screen.getByLabelText('fikra')).toHaveValue('5')
    expect(screen.getByLabelText('bent')).toHaveValue('a')
  })

  it('keeps ambiguous madde unchanged after blur and keeps showing the error', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    const maddeInput = screen.getByLabelText('madde')
    await user.type(maddeInput, '17--a')
    fireEvent.blur(maddeInput)

    expect(maddeInput).toHaveValue('17--a')
    expect(maddeInput).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Madde formatı belirsiz. Örn: 17/5-a.')).toBeInTheDocument()
  })

  it('shows a bent cleanup warning and normalizes bent on blur', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    const bentInput = screen.getByLabelText('bent')
    await user.type(bentInput, '(A)')
    expect(screen.getByText('Kaydedilirken a olarak düzeltilecek.')).toBeInTheDocument()

    fireEvent.blur(bentInput)
    expect(bentInput).toHaveValue('a')
  })
})
