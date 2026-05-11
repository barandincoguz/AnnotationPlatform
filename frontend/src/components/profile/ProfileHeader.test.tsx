import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProfileHeader } from './ProfileHeader'

describe('ProfileHeader', () => {
  it('renders username with @ prefix', () => {
    render(<ProfileHeader user={{ id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' }} createdAt="2026-05-01T00:00:00+00:00" />)
    expect(screen.getByText('@tester')).toBeInTheDocument()
  })

  it('renders role badge', () => {
    render(<ProfileHeader user={{ id: 1, username: 'admin1', role: 'admin', avatar_color: '#3b82f6' }} createdAt="2026-05-01T00:00:00+00:00" />)
    expect(screen.getByText(/Yönetici/)).toBeInTheDocument()
  })

  it('renders created date in Turkish locale', () => {
    render(<ProfileHeader user={{ id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' }} createdAt="2026-05-01T00:00:00+00:00" />)
    expect(screen.getByText(/Hesap oluşturuldu/)).toBeInTheDocument()
  })

  it('uses avatar_color as background', () => {
    render(<ProfileHeader user={{ id: 1, username: 'tester', role: 'user', avatar_color: '#ef4444' }} createdAt="2026-05-01T00:00:00+00:00" />)
    const avatar = screen.getByText('T')
    expect(avatar.getAttribute('style')).toContain('background-color')
  })
})
