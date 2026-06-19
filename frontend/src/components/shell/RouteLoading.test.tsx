import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { RouteLoading } from './RouteLoading'

describe('RouteLoading', () => {
  it('announces lazy route loading without taking over the full viewport', () => {
    renderWithProviders(<RouteLoading />)

    expect(screen.getByRole('status')).toHaveTextContent('Sayfa yükleniyor…')
    expect(screen.getByRole('status')).not.toHaveClass('min-h-screen')
  })
})
