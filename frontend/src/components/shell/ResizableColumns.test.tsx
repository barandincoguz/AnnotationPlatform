import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResizableColumns } from './ResizableColumns'

describe('ResizableColumns', () => {
  it('renders three regions: left, middle, right', () => {
    render(
      <ResizableColumns
        left={<div>LEFT-CONTENT</div>}
        middle={<div>MIDDLE-CONTENT</div>}
        right={<div>RIGHT-CONTENT</div>}
      />,
    )
    expect(screen.getByText('LEFT-CONTENT')).toBeInTheDocument()
    expect(screen.getByText('MIDDLE-CONTENT')).toBeInTheDocument()
    expect(screen.getByText('RIGHT-CONTENT')).toBeInTheDocument()
  })
})
