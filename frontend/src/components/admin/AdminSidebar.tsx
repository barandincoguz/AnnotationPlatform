import { NavLink } from 'react-router-dom'
import { adminNavGroups } from './adminNav'

export function AdminSidebar() {
  return (
    <nav
      aria-label="Admin"
      className="hidden lg:flex lg:w-60 lg:flex-col lg:border-r lg:border-border/70 lg:bg-card/40"
    >
      <div className="px-5 pt-6 pb-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          № 11
        </p>
        <h2 className="mt-1 font-display text-xl font-medium tracking-tight text-foreground">
          Yönetici Paneli
        </h2>
      </div>
      <ul className="flex flex-1 flex-col gap-5 px-3 pb-6">
        {adminNavGroups.map((g) => (
          <li key={g.label}>
            <div className="px-3 pb-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {g.label}
            </div>
            <ul className="flex flex-col gap-px">
              {g.items.map((it) => (
                <li key={it.to}>
                  <NavLink
                    to={it.to}
                    className={({ isActive }) =>
                      [
                        'group relative flex items-center rounded-md px-3 py-1.5 text-sm transition-colors',
                        isActive
                          ? 'bg-secondary text-foreground font-medium'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted/60',
                      ].join(' ')
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span
                            aria-hidden
                            className="absolute inset-y-1.5 left-0 w-[2px] bg-accent rounded-r"
                          />
                        )}
                        <span>{it.label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <div className="border-t border-border/60 px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
        2026 · Murat Karakaya Akademi
      </div>
    </nav>
  )
}
