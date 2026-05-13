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
import { adminNavGroups } from './adminNav'

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
          {adminNavGroups.map((g) => (
            <SelectGroup key={g.label}>
              <SelectLabel>{g.label}</SelectLabel>
              {g.items.map((it) => (
                <SelectItem key={it.to} value={it.to}>
                  {it.label}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
