import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HelpAccordion } from './HelpAccordion'

const sections = [
  { id: '01-welcome', order: 1, title: 'Hoş geldin', body: '# Hoş geldin\n\nMerhaba.' },
  { id: '02-getting-started', order: 2, title: 'Başlarken', body: '# Başlarken\n\ni̇lk adım.' },
  { id: '03-annotation-guide', order: 3, title: 'Anotasyon', body: '# Anotasyon\n\nReferans ekle.' },
]

describe('HelpAccordion', () => {
  it('renders all section titles as triggers', () => {
    render(<HelpAccordion sections={sections} />)
    expect(screen.getByRole('button', { name: /hoş geldin/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /başlarken/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /anotasyon/i })).toBeInTheDocument()
  })

  it('has first section expanded by default', () => {
    render(<HelpAccordion sections={sections} />)
    expect(screen.getByText(/merhaba/i)).toBeInTheDocument()
  })

  it('expands additional sections without collapsing the first', async () => {
    const user = userEvent.setup()
    render(<HelpAccordion sections={sections} />)
    expect(screen.queryByText(/i̇lk adım/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /başlarken/i }))
    expect(screen.getByText(/i̇lk adım/i)).toBeInTheDocument()
    expect(screen.getByText(/merhaba/i)).toBeInTheDocument()
  })

  it('renders empty when sections is empty', () => {
    const { container } = render(<HelpAccordion sections={[]} />)
    expect(container.querySelector('[data-state]')).toBeNull()
  })

  it('respects ordering by `order` field', () => {
    const unsorted = [
      { ...sections[2], order: 2 },
      { ...sections[0], order: 1 },
      { ...sections[1], order: 3 },
    ]
    render(<HelpAccordion sections={unsorted as typeof sections} />)
    const triggers = screen.getAllByRole('button')
    expect(triggers[0]).toHaveTextContent(/hoş geldin/i)
    expect(triggers[1]).toHaveTextContent(/anotasyon/i)
    expect(triggers[2]).toHaveTextContent(/başlarken/i)
  })
})
