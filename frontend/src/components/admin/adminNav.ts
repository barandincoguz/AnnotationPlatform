export interface AdminNavItem {
  to: string
  label: string
}

export interface AdminNavGroup {
  label: string
  items: AdminNavItem[]
}

export const adminNavGroups: AdminNavGroup[] = [
  {
    label: 'Operations',
    items: [
      { to: '/admin/audit', label: 'Audit' },
      { to: '/admin/events', label: 'Events' },
      { to: '/admin/locks', label: 'Locks' },
      { to: '/admin/mirror', label: 'Mirror health' },
      { to: '/admin/backup', label: 'Backup' },
      { to: '/admin/retention', label: 'Retention' },
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
