 
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { server } from '@/test/msw-server'
import { GoldDocsPage } from './GoldDocsPage'

const Wrap = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <Toaster />
    <GoldDocsPage />
  </QueryClientProvider>
)

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/admin/training/gold-docs', () => HttpResponse.json({
      resolved: [
        { gold_id: 'g_a', content: 'doc A', expected_concepts: [{ kanun_no: '5520', madde: '5' }], min_concept_count: 1 },
      ],
      overrides: [],
    })),
  )
})

describe('GoldDocsPage', () => {
  it('lists gold docs and shows editor on click', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('g_a')).toBeInTheDocument())
    await user.click(screen.getByText('g_a'))
    expect(screen.getByDisplayValue('doc A')).toBeInTheDocument()
    expect(screen.getByDisplayValue('5520')).toBeInTheDocument()
  })

  it('save opens DiffPreviewDialog and requires OVERRIDE typed', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('g_a')).toBeInTheDocument())
    await user.click(screen.getByText('g_a'))
    const contentTa = screen.getByLabelText(/İçerik/i)
    await user.clear(contentTa)
    await user.type(contentTa, 'doc A2')
    await user.click(screen.getByRole('button', { name: /^kaydet$/i }))
    expect(screen.getByLabelText(/OVERRIDE yazınız/i)).toBeInTheDocument()
  })

  it('blocks save if concept missing kanun_no', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('g_a')).toBeInTheDocument())
    await user.click(screen.getByText('g_a'))
    await user.clear(screen.getByDisplayValue('5520'))
    expect(screen.getByRole('button', { name: /^kaydet$/i })).toBeDisabled()
  })
})
