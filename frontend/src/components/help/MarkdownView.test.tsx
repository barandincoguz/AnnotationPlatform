import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MarkdownView } from './MarkdownView'

describe('MarkdownView', () => {
  it('renders h1', () => {
    render(<MarkdownView>{`# Hoş geldin`}</MarkdownView>)
    expect(screen.getByRole('heading', { level: 1, name: /hoş geldin/i })).toBeInTheDocument()
  })

  it('renders h2 and paragraphs', () => {
    render(<MarkdownView>{`## Başlık\n\nBir paragraf.`}</MarkdownView>)
    expect(screen.getByRole('heading', { level: 2, name: /başlık/i })).toBeInTheDocument()
    expect(screen.getByText(/bir paragraf\./i)).toBeInTheDocument()
  })

  it('renders unordered list', () => {
    render(<MarkdownView>{`- item 1\n- item 2`}</MarkdownView>)
    const items = screen.getAllByRole('listitem')
    expect(items.length).toBeGreaterThanOrEqual(2)
  })

  it('renders inline code', () => {
    const { container } = render(<MarkdownView>{`Use \`npm test\` to run.`}</MarkdownView>)
    expect(container.querySelector('code')).not.toBeNull()
  })

  it('renders GFM table', () => {
    const md = '| a | b |\n| - | - |\n| 1 | 2 |'
    const { container } = render(<MarkdownView>{md}</MarkdownView>)
    expect(container.querySelector('table')).not.toBeNull()
  })

  it('XSS: strips <script> tags from body', () => {
    const dangerous = `# Title\n\n<script>window.__xss__ = true</script>\n\nBody.`
    const { container } = render(<MarkdownView>{dangerous}</MarkdownView>)
    expect(container.querySelector('script')).toBeNull()
    expect(screen.queryByText(/window\.__xss__/)).toBeNull()
  })

  it('XSS: strips on* handlers from elements', () => {
    const dangerous = `<img src="x" onerror="window.__xss__=true">`
    const { container } = render(<MarkdownView>{dangerous}</MarkdownView>)
    const img = container.querySelector('img')
    // After sanitize, either <img> is stripped entirely OR onerror attribute is removed.
    // Both outcomes are acceptable; neither leaks the handler.
    expect(img?.getAttribute('onerror') ?? null).toBeNull()
  })
})
