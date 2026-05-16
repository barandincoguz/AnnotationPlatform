import { Link, Outlet } from 'react-router-dom'
import { AdminSidebar } from '@/components/admin/AdminSidebar'
import { AdminMobileNav } from '@/components/admin/AdminMobileNav'

export function AdminLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#admin-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:px-3 focus:py-2 focus:shadow"
      >
        içeriğe atla
      </a>

      {/* Brand header — provides return-to-home from admin */}
      <header
        role="banner"
        className="sticky top-0 z-30 h-14 border-b border-border/70 bg-background/85 backdrop-blur-md px-5 flex items-center justify-between"
      >
        <Link
          to="/"
          aria-label="Anotasyon ana sayfasına dön"
          className="group inline-flex items-center gap-3 outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md transition-opacity"
        >
          <span
            aria-hidden
            className="grid h-8 w-8 place-items-center rounded-md border border-border bg-card font-display text-base font-semibold text-foreground transition-colors group-hover:border-accent group-hover:text-accent"
          >
            A
          </span>
          <span className="flex flex-col leading-tight">
            <span className="font-display text-[15px] font-semibold tracking-tight text-foreground">
              Anotasyon Platformu
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Yönetici Paneli · Admin
            </span>
          </span>
        </Link>
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/80 hidden sm:block">
          v0.1.0
        </div>
      </header>

      <div className="flex flex-1 min-h-0 flex-col lg:flex-row">
        <AdminSidebar />
        <AdminMobileNav />
        <main id="admin-main" className="flex-1 p-4 lg:p-8 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
