 
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AdminTable } from './AdminTable'

interface Row { id: number; name: string; role: string }

const rows: Row[] = [
  { id: 1, name: 'alice', role: 'admin' },
  { id: 2, name: 'bob', role: 'user' },
]

describe('AdminTable', () => {
  it('renders headers and rows', () => {
    render(
      <AdminTable<Row>
        rows={rows}
        getRowKey={(r) => r.id}
        columns={[
          { key: 'name', header: 'Ad', render: (r) => r.name },
          { key: 'role', header: 'Rol', render: (r) => r.role },
        ]}
      />,
    )
    expect(screen.getByRole('columnheader', { name: 'Ad' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Rol' })).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('renders empty state with custom message', () => {
    render(
      <AdminTable<Row>
        rows={[]}
        getRowKey={(r) => r.id}
        columns={[{ key: 'name', header: 'Ad', render: (r) => r.name }]}
        emptyMessage="Hiç kayıt yok"
      />,
    )
    expect(screen.getByText('Hiç kayıt yok')).toBeInTheDocument()
  })

  it('renders loading skeleton when loading prop true', () => {
    render(
      <AdminTable<Row>
        rows={[]}
        getRowKey={(r) => r.id}
        columns={[{ key: 'name', header: 'Ad', render: (r) => r.name }]}
        loading
      />,
    )
    expect(screen.getAllByTestId('admin-table-skeleton-row').length).toBeGreaterThan(0)
  })
})
