import { useNavigate, useLocation } from 'react-router-dom'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const options = [
  {
    group: 'Operations',
    items: [
      { v: '/admin/audit', l: 'Audit' },
      { v: '/admin/events', l: 'Events' },
      { v: '/admin/locks', l: 'Locks' },
    ],
  },
  { group: 'People', items: [{ v: '/admin/users', l: 'Users' }] },
  { group: 'Platform', items: [{ v: '/admin/settings', l: 'Settings' }] },
  {
    group: 'Training Content',
    items: [
      { v: '/admin/training/gold-docs', l: 'Gold Docs' },
      { v: '/admin/training/quiz', l: 'Quiz' },
    ],
  },
]

export function AdminMobileNav() {
  const navigate = useNavigate()
  const location = useLocation()
  return (
    <div className="border-b p-2 lg:hidden">
      <Select value={location.pathname} onValueChange={(v) => navigate(v)}>
        <SelectTrigger aria-label="Admin sayfası seç">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((g) => (
            <SelectGroup key={g.group}>
              <SelectLabel>{g.group}</SelectLabel>
              {g.items.map((it) => (
                <SelectItem key={it.v} value={it.v}>
                  {it.l}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
