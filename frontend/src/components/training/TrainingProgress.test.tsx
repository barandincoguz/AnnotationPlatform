import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TrainingProgress } from './TrainingProgress'

describe('TrainingProgress', () => {
  it('renders 5 labeled pills', () => {
    render(<TrainingProgress step="quiz" docIndex={0} />)
    expect(screen.getByText(/quiz/i)).toBeInTheDocument()
    expect(screen.getByText(/doc 1/i)).toBeInTheDocument()
    expect(screen.getByText(/doc 2/i)).toBeInTheDocument()
    expect(screen.getByText(/doc 3/i)).toBeInTheDocument()
    expect(screen.getByText(/sonuç/i)).toBeInTheDocument()
  })

  it('quiz step → aria-current on Quiz pill', () => {
    const { container } = render(<TrainingProgress step="quiz" docIndex={0} />)
    const current = container.querySelector('[aria-current="step"]')
    expect(current?.textContent).toMatch(/quiz/i)
  })

  it('doc step docIndex=1 → aria-current on Doc 2 pill', () => {
    const { container } = render(<TrainingProgress step="doc" docIndex={1} />)
    const current = container.querySelector('[aria-current="step"]')
    expect(current?.textContent).toMatch(/doc 2/i)
  })

  it('summary step → aria-current on Sonuç pill', () => {
    const { container } = render(<TrainingProgress step="summary" docIndex={0} />)
    const current = container.querySelector('[aria-current="step"]')
    expect(current?.textContent).toMatch(/sonuç/i)
  })

  it('idle step → no aria-current', () => {
    const { container } = render(<TrainingProgress step="idle" docIndex={0} />)
    expect(container.querySelector('[aria-current="step"]')).toBeNull()
  })
})
