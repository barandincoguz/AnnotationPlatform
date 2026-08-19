import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReactElement } from 'react'

import { DocViewer } from '@/components/annotation/DocViewer'
import { makeDocumentDetail } from '@/test/msw-handlers'
// Shared server: src/test/setup.ts owns listen()/resetHandlers()/close().
import { server } from '@/test/msw-server'

const PDF_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi\nhukmu duzenlenmistir."

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/documents/d1', () =>
      HttpResponse.json(makeDocumentDetail({ document_id: 'd1', pdf_text: PDF_TEXT })),
    ),
  )
})

function renderViewer(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DocViewer highlights', () => {
  it('renders plain text when no highlights are given', async () => {
    renderViewer(<DocViewer docId="d1" />)
    await waitFor(() => expect(screen.getByText(/zamanasimi/)).toBeInTheDocument())
    expect(document.querySelector('mark')).toBeNull()
  })

  it('marks a quote whose newline was collapsed by the model', async () => {
    renderViewer(
      <DocViewer
        docId="d1"
        highlights={[{ id: 'm1', quote: 'zamanasimi hukmu duzenlenmistir' }]}
      />,
    )
    await waitFor(() => expect(document.querySelector('mark')).not.toBeNull())
    const mark = document.querySelector('mark')!
    expect(mark.getAttribute('data-highlight-id')).toBe('m1')
    expect(mark.textContent).toBe('zamanasimi\nhukmu duzenlenmistir')
  })

  it('scrolls the active highlight into view', async () => {
    const scrollIntoView = vi.fn()
    window.HTMLElement.prototype.scrollIntoView = scrollIntoView
    renderViewer(
      <DocViewer
        docId="d1"
        highlights={[{ id: 'm1', quote: 'zamanasimi hukmu duzenlenmistir' }]}
        activeHighlightId="m1"
      />,
    )
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled())
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  })

  it('leaves the document intact when the quote cannot be located', async () => {
    renderViewer(
      <DocViewer docId="d1" highlights={[{ id: 'ghost', quote: 'yok boyle bir cumle' }]} />,
    )
    await waitFor(() => expect(screen.getByText(/zamanasimi/)).toBeInTheDocument())
    expect(document.querySelector('mark')).toBeNull()
  })
})
