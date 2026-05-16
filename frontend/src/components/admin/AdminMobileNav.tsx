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
    <div className="border-b border-border/70 bg-card/40 px-4 py-3 lg:hidden">
      <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        Yönetici Paneli
      </p>
      <Select value={location.pathname} onValueChange={(v) => navigate(v)}>
        <SelectTrigger aria-label="Admin sayfası seç" className="h-10 bg-card">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {adminNavGroups.map((g) => (
            <SelectGroup key={g.label}>
              <SelectLabel className="font-mono text-[10px] uppercase tracking-[0.18em]">
                {g.label}
              </SelectLabel>
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
