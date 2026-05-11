import { Outlet } from 'react-router-dom'

export function AppShell() {
  // Minimal in 16a — TopBar with XP/streak/online users lands in 16d.
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b px-4 py-2 flex items-center justify-between">
        <span className="font-semibold">Anotasyon Platformu</span>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}
