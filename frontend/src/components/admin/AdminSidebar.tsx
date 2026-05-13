import { NavLink } from 'react-router-dom'

const groups = [
  {
    label: 'Operations',
    items: [
      { to: '/admin/audit', label: 'Audit' },
      { to: '/admin/events', label: 'Events' },
      { to: '/admin/locks', label: 'Locks' },
    ],
  },
  { label: 'People', items: [{ to: '/admin/users', label: 'Users' }] },
  { label: 'Platform', items: [{ to: '/admin/settings', label: 'Settings' }] },
  {
    label: 'Training Content',
    items: [
      { to: '/admin/training/gold-docs', label: 'Gold Docs' },
      { to: '/admin/training/quiz', label: 'Quiz' },
    ],
  },
]

export function AdminSidebar() {
  return (
    <nav aria-label="Admin" className="hidden lg:flex lg:w-56 lg:flex-col lg:border-r lg:bg-muted/30">
      <div className="p-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        Yönetici Paneli
      </div>
      <ul className="flex flex-1 flex-col gap-4 px-2 pb-4">
        {groups.map((g) => (
          <li key={g.label}>
            <div className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
              {g.label}
            </div>
            <ul className="flex flex-col gap-0.5">
              {g.items.map((it) => (
                <li key={it.to}>
                  <NavLink
                    to={it.to}
                    className={({ isActive }) =>
                      `block rounded px-3 py-1.5 text-sm hover:bg-muted ${
                        isActive ? 'bg-muted font-medium' : ''
                      }`
                    }
                  >
                    {it.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </nav>
  )
}
