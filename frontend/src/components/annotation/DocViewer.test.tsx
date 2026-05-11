import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { makeDocumentDetail } from '@/test/msw-handlers'
import { DocViewer } from './DocViewer'

describe('DocViewer', () => {
  it('renders doc metadata header + pdf_text body', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-1', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-1',
            sayi: 9999,
            tarih: '2025-05-22',
            vergi_turu: 'ÖTV',
            pdf_text: 'BELGE GÖVDESİ İÇERİĞİ',
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-1" />)
    await waitFor(() => expect(screen.getByText(/9999/)).toBeInTheDocument())
    expect(screen.getByText(/ÖTV/i)).toBeInTheDocument()
    expect(screen.getByText(/BELGE GÖVDESİ/i)).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    server.use(
      http.get('http://localhost/api/documents/doc-2', async () => {
        await new Promise((r) => setTimeout(r, 500))
        return HttpResponse.json(makeDocumentDetail({ document_id: 'doc-2' }))
      }),
    )
    renderWithProviders(<DocViewer docId="doc-2" />)
    expect(screen.getByText(/yükleniyor/i)).toBeInTheDocument()
  })
})
