import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { LawAbbreviationList } from './LawAbbreviationList'

const API = 'http://localhost'

describe('LawAbbreviationList', () => {
  it('renders canonical law rows from the API', async () => {
    renderWithProviders(<LawAbbreviationList />)
    expect(await screen.findByText('Vergi Usul Kanunu')).toBeInTheDocument()
    expect(screen.getByText('Katma Değer Vergisi Kanunu')).toBeInTheDocument()
    expect(screen.getByText('Kurumlar Vergisi Kanunu')).toBeInTheDocument()
    // abbreviation + number shown
    expect(screen.getByText('VUK')).toBeInTheDocument()
    expect(screen.getByText('213')).toBeInTheDocument()
  })

  it('filters by abbreviation', async () => {
    renderWithProviders(<LawAbbreviationList />)
    await screen.findByText('Vergi Usul Kanunu')
    await userEvent.type(screen.getByLabelText('Kısaltma ara'), 'KDV')
    await waitFor(() => {
      expect(screen.getByText('Katma Değer Vergisi Kanunu')).toBeInTheDocument()
      expect(screen.queryByText('Vergi Usul Kanunu')).not.toBeInTheDocument()
    })
  })

  it('filters by law number', async () => {
    renderWithProviders(<LawAbbreviationList />)
    await screen.findByText('Vergi Usul Kanunu')
    await userEvent.type(screen.getByLabelText('Kısaltma ara'), '213')
    await waitFor(() => {
      expect(screen.getByText('Vergi Usul Kanunu')).toBeInTheDocument()
      expect(screen.queryByText('Kurumlar Vergisi Kanunu')).not.toBeInTheDocument()
    })
  })

  it('shows empty state when nothing matches', async () => {
    renderWithProviders(<LawAbbreviationList />)
    await screen.findByText('Vergi Usul Kanunu')
    await userEvent.type(screen.getByLabelText('Kısaltma ara'), 'zzzzz')
    expect(await screen.findByText('Eşleşen kısaltma yok.')).toBeInTheDocument()
  })

  it('shows an error state when the request fails', async () => {
    server.use(http.get(`${API}/api/law-abbreviations`, () => HttpResponse.error()))
    renderWithProviders(<LawAbbreviationList />)
    expect(await screen.findByText('Kısaltmalar yüklenemedi.')).toBeInTheDocument()
  })
})
