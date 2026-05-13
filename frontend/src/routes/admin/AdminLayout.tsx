import { Outlet } from 'react-router-dom'
import { AdminSidebar } from '@/components/admin/AdminSidebar'
import { AdminMobileNav } from '@/components/admin/AdminMobileNav'

export function AdminLayout() {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <a
        href="#admin-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2 focus:shadow"
      >
        içeriğe atla
      </a>
      <AdminSidebar />
      <AdminMobileNav />
      <main id="admin-main" className="flex-1 p-4 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
