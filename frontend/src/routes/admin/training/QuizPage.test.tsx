 
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { server } from '@/test/msw-server'
import { QuizPage } from './QuizPage'

const Wrap = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <Toaster />
    <QuizPage />
  </QueryClientProvider>
)

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/admin/training/quiz', () => HttpResponse.json({
      resolved: [
        {
          id: 'q1',
          text: 'KVK kısaltması ne anlama gelir?',
          choices: ['Katma Değer', 'Kurumlar Vergisi Kanunu', 'Kira Vergi', 'Konut Vergi'],
          correct_choice_idx: 1,
        },
      ],
      overrides: [],
    })),
  )
})

describe('QuizPage', () => {
  it('lists quiz questions and shows editor on click', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('q1')).toBeInTheDocument())
    await user.click(screen.getByText('q1'))
    expect(screen.getByDisplayValue(/KVK kısaltması/)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Kurumlar Vergisi Kanunu')).toBeInTheDocument()
  })

  it('save opens DiffPreviewDialog and requires OVERRIDE typed', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('q1')).toBeInTheDocument())
    await user.click(screen.getByText('q1'))
    const textarea = screen.getByLabelText(/soru metni/i)
    await user.clear(textarea)
    await user.type(textarea, 'KVK kısaltması nedir?')
    await user.click(screen.getByRole('button', { name: /^kaydet$/i }))
    expect(screen.getByLabelText(/OVERRIDE yazınız/i)).toBeInTheDocument()
  })

  it('blocks save if any choice is empty', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('q1')).toBeInTheDocument())
    await user.click(screen.getByText('q1'))
    await user.clear(screen.getByDisplayValue('Kurumlar Vergisi Kanunu'))
    expect(screen.getByRole('button', { name: /^kaydet$/i })).toBeDisabled()
  })
})
