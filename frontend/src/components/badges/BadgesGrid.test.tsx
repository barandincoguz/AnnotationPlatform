/* eslint-disable react/display-name -- test wrappers, no display name needed */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { BadgesGrid } from './BadgesGrid'
import { defaultBadgesCatalog, makeProfile } from '@/test/msw-handlers'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('BadgesGrid', () => {
  it('defaults to "Kazanılmış" tab when user has earned badges', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile())),
    )
    render(<BadgesGrid />, { wrapper: wrap() })
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Kazanılmış/ })).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('defaults to "Hepsi" tab when user has zero earned badges', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
    )
    render(<BadgesGrid />, { wrapper: wrap() })
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Hepsi/ })).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('"Hepsi" tab shows all 7 cards', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
    )
    const user = userEvent.setup()
    render(<BadgesGrid />, { wrapper: wrap() })
    const hepsi = await screen.findByRole('tab', { name: /Hepsi/ })
    await user.click(hepsi)
    // 7 catalog entries → 7 Kilitli aria-labels (locked variant)
    await waitFor(() => {
      const lockedIcons = screen.getAllByLabelText('Kilitli')
      expect(lockedIcons.length).toBe(7)
    })
  })

  it('on catalog fetch error, shows Kazanılmış-only + warning', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile())),
    )
    render(<BadgesGrid />, { wrapper: wrap() })
    expect(await screen.findByText(/Tüm rozet kataloğu yüklenemedi/)).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /Hepsi/ })).not.toBeInTheDocument()
  })

  it('empty Kazanılmış tab shows helper text', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
    )
    const user = userEvent.setup()
    render(<BadgesGrid />, { wrapper: wrap() })
    const kazanilmis = await screen.findByRole('tab', { name: /Kazanılmış/ })
    await user.click(kazanilmis)
    expect(await screen.findByText(/Henüz rozet yok/)).toBeInTheDocument()
  })
})
