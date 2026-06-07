import { describe, it, expect } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
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
            tarih: '2025-05-22',
            vergi_turu: 'ÖTV',
            pdf_text: 'BELGE GÖVDESİ İÇERİĞİ',
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-1" />)
    // Header now leads with document_id; sayi is no longer rendered.
    await waitFor(() => expect(screen.getByText('doc-1')).toBeInTheDocument())
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

  it('exposes the document_id (evrakOid) in the header (paket-6d)', async () => {
    server.use(
      http.get('http://localhost/api/documents/17h2sm8cdz11kq', () =>
        HttpResponse.json(makeDocumentDetail({ document_id: '17h2sm8cdz11kq' })),
      ),
    )
    renderWithProviders(<DocViewer docId="17h2sm8cdz11kq" />)
    await waitFor(() => expect(screen.getByText('17h2sm8cdz11kq')).toBeInTheDocument())
  })

  it('formats tarih and basvuru_tarihi as Turkish dd.mm.yyyy (paket-6e)', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-3', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-3',
            tarih: '20260123',
            basvuru_tarihi: '20250604',
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-3" />)
    await waitFor(() => expect(screen.getByText('23.01.2026')).toBeInTheDocument())
    expect(screen.getByText('04.06.2025')).toBeInTheDocument()
  })

  it('renders kanun_refs in a list with sequence numbering (paket-6a)', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-r', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-r',
            kanun_refs: [
              { seq: 0, kanun_kodu: '193 - GELİR VERGİSİ KANUNU', kanun_maddesi: '37', kanun_maddesi_turu: 'ASIL' },
              { seq: 1, kanun_kodu: '193 - GELİR VERGİSİ KANUNU', kanun_maddesi: '70', kanun_maddesi_turu: 'ASIL' },
            ],
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-r" />)
    await waitFor(() => expect(screen.getByText(/Kaynak Veri Referansları/i)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/Kaynak Veri Referansları/i))
    await waitFor(() => expect(screen.getByText(/kanun bilgileri/i)).toBeInTheDocument())
    // Multiple kanun rows share the kodu string; assert both maddeler appear.
    expect(screen.getByText(/Madde 37/)).toBeInTheDocument()
    expect(screen.getByText(/Madde 70/)).toBeInTheDocument()
    // Each row prefixed with zero-padded sequence number.
    expect(screen.getByText('01.')).toBeInTheDocument()
    expect(screen.getByText('02.')).toBeInTheDocument()
  })

  it('renders bkk_refs separately with their türü', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-b', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-b',
            bkk_refs: [
              { seq: 0, turu: 'TEBLİĞ', kanun_kodu: '193 - GELİR VERGİSİ KANUNU', madde_no: '325' },
            ],
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-b" />)
    await waitFor(() => expect(screen.getByText(/Kaynak Veri Referansları/i)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/Kaynak Veri Referansları/i))
    await waitFor(() => expect(screen.getByText(/BKK \/ Tebliğ \/ Sirküler/i)).toBeInTheDocument())
    expect(screen.getByText('TEBLİĞ')).toBeInTheDocument()
    expect(screen.getByText(/Madde 325/)).toBeInTheDocument()
  })

  it('warns annotators that source-data refs are unreliable (paket-6g)', async () => {
    // Whole project exists because the upstream kanun/bkk lists are
    // known-bad; the panel must carry a destructive banner so no one
    // treats them as ground truth.
    server.use(
      http.get('http://localhost/api/documents/doc-warn', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-warn',
            kanun_refs: [
              { seq: 0, kanun_kodu: '193', kanun_maddesi: '37', kanun_maddesi_turu: 'ASIL' },
            ],
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-warn" />)
    await waitFor(() => expect(screen.getByText(/Kaynak Veri Referansları/i)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/Kaynak Veri Referansları/i))
    const warning = await screen.findByTestId('refs-source-warning')
    expect(warning).toBeInTheDocument()
    expect(warning.textContent).toMatch(/güvensiz/i)
    expect(warning.className).toMatch(/destructive/)
  })

  it('hides the reference section AND the warning when there are no refs', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-empty', () =>
        HttpResponse.json(makeDocumentDetail({ document_id: 'doc-empty' })),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-empty" />)
    await waitFor(() => expect(screen.getByText(/doc-empty/i)).toBeInTheDocument())
    expect(screen.queryByText(/kanun bilgileri/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/bkk \/ tebliğ/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('refs-source-warning')).not.toBeInTheDocument()
  })

  it('normalizes pdf_text double-spaces and trailing whitespace (paket-6c)', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-ws', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-ws',
            pdf_text: 'tesis  edildiği,  evinizin  Altuntaş',
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-ws" />)
    await waitFor(() =>
      expect(screen.getByText(/tesis edildiği, evinizin Altuntaş/)).toBeInTheDocument(),
    )
    // Raw double-spaced version must NOT survive into the DOM.
    expect(screen.queryByText(/tesis {2}edildiği/)).not.toBeInTheDocument()
  })

  it('renders difficulty badge with semantic color', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-d', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-d',
            estimated_difficulty: 'Orta',
          }),
        ),
      ),
    )
    renderWithProviders(<DocViewer docId="doc-d" />)
    await waitFor(() => expect(screen.getByText('Orta')).toBeInTheDocument())
    expect(screen.getByText('Orta').className).toMatch(/warning/)
  })
})
