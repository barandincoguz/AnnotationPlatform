import { Outlet } from 'react-router-dom'
import { TopBar } from '@/components/topbar/TopBar'

export function AppShell() {
  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <main className="flex-1 min-h-0">
        <Outlet />
      </main>
    </div>
  )
}
