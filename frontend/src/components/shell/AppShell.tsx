import { Outlet } from 'react-router-dom'
import { TopBar } from '@/components/topbar/TopBar'

export function AppShell() {
  return (
    <div className="min-h-screen flex flex-col">
      {/*
        Keyboard users land here first; they shouldn't have to Tab
        through the entire TopBar (XP, streak, daily progress, online
        users, profile dropdown — roughly 10 stops) before reaching
        the doc list. Matches the pattern AdminLayout uses for its own
        skip-link.
      */}
      <a
        href="#annotate-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:px-3 focus:py-2 focus:shadow"
      >
        içeriğe atla
      </a>
      <TopBar />
      <main id="annotate-main" className="flex-1 min-h-0">
        <Outlet />
      </main>
    </div>
  )
}
