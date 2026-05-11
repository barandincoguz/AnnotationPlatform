import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="text-3xl font-semibold">404</p>
      <p className="text-muted-foreground">Sayfa bulunamadı</p>
      <Button asChild>
        <Link to="/">Ana sayfaya dön</Link>
      </Button>
    </div>
  )
}
