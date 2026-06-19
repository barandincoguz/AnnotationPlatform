import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BrandLogo } from '@/components/shell/BrandLogo'
import { ApiError } from '@/api/client'

// Hoisted to module scope so typing into the username/password fields
// (which fires per-keystroke state updates) doesn't allocate a new
// style object and re-apply identical CSS each render.
const ASIDE_BACKGROUND: React.CSSProperties = {
  background:
    'radial-gradient(at 12% 12%, hsl(32 60% 92% / 0.85) 0px, transparent 55%),' +
    'radial-gradient(at 88% 18%, hsl(175 45% 90% / 0.7) 0px, transparent 50%),' +
    'radial-gradient(at 50% 100%, hsl(222 35% 94% / 0.8) 0px, transparent 60%),' +
    'hsl(var(--card) / 0.6)',
}

export function Login() {
  const { loginMutation } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const navigationState = location.state as unknown
  const registeredUsername =
    typeof navigationState === 'object' &&
    navigationState !== null &&
    'registeredUsername' in navigationState &&
    typeof navigationState.registeredUsername === 'string'
      ? navigationState.registeredUsername
      : ''
  const [username, setUsername] = useState(registeredUsername)
  const [password, setPassword] = useState('')
  const disabled = username.trim().length === 0 || password.length === 0

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    loginMutation.mutate({ username: username.trim(), password }, { onSuccess: () => navigate('/') })
  }

  const errorMessage =
    loginMutation.error instanceof ApiError
      ? loginMutation.error.message
      : loginMutation.isError
        ? 'Giriş yapılamadı'
        : null

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr] bg-background">
      {/* Editorial aside — warm reading-room cover with layered atmosphere */}
      <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r border-border/60 grain px-12 py-14 xl:px-16">
        {/* Layered gradient wash — three soft pools of color make the aside
            feel inhabited rather than printed. */}
        <div
          aria-hidden
          className="absolute inset-0 -z-10"
          style={ASIDE_BACKGROUND}
        />
        <div className="relative z-10 flex items-center justify-between">
          <div className="inline-flex items-center gap-3">
            <BrandLogo className="h-9 w-[2.85rem] text-foreground" />
            <span className="font-display text-[18px] font-bold tracking-tight text-foreground">
              Anotasyon Platformu
            </span>
          </div>
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            001
          </span>
        </div>

        <div className="relative z-10 max-w-xl space-y-8">
          <p className="rise-in rise-1 font-mono text-[12px] font-semibold uppercase tracking-[0.24em] text-accent">
            Bursiyer girişi
          </p>
          <h1 className="rise-in rise-2 font-display text-[3.5rem] xl:text-[4.25rem] font-bold leading-[0.95] tracking-tight text-foreground">
            Türk vergi hukukuna
            <br />
            <em className="font-medium italic text-accent">titiz bir bakış.</em>
          </h1>
          <p className="rise-in rise-3 max-w-md text-[17px] leading-relaxed text-foreground/75">
            Özelgelerden kanun atfı çıkarımı: bursiyer ekibinin titizlikle hazırladığı,
            vergi pratisyenleri için bir referans kütüphanesi.
          </p>
          <div className="rise-in rise-4 flex items-center gap-4 pt-2 font-mono text-[12px] font-semibold uppercase tracking-[0.2em] text-foreground/75">
            <span className="inline-flex items-center gap-2">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-accent" />
              17.923 özelge
            </span>
            <span className="h-px w-6 bg-border" aria-hidden />
            <span className="inline-flex items-center gap-2">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-accent2" />
              kanun atfı çıkarımı
            </span>
          </div>
        </div>

        <div className="relative z-10 flex items-baseline justify-between font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground/70">
          <span>v0.1.0</span>
          <span>2026 — Murat Karakaya Akademi</span>
        </div>
      </aside>

      {/* Form panel */}
      <main className="relative flex items-center justify-center overflow-hidden px-6 py-10 sm:px-10 lg:px-14">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 wash-amber"
        />
        <div className="w-full max-w-sm space-y-10">
          <header className="rise-in rise-1 space-y-3">
            <p className="font-mono text-[12px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Giriş
            </p>
            <h2 className="font-display text-5xl font-bold leading-[1.05] tracking-tight">
              Tekrar
              <br />
              hoş geldin.
            </h2>
          </header>

          <form onSubmit={handleSubmit} className="rise-in rise-2 space-y-5" noValidate>
            <div className="space-y-2">
              <Label htmlFor="username">Kullanıcı adı</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="h-12 bg-card text-base"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Şifre</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="h-12 bg-card text-base"
              />
            </div>

            {errorMessage && (
              <p
                className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-[15px] font-medium text-destructive"
                role="alert"
              >
                {errorMessage}
              </p>
            )}

            <Button
              type="submit"
              disabled={disabled || loginMutation.isPending}
              size="lg"
              className="w-full text-base tracking-wide"
            >
              {loginMutation.isPending ? 'Giriş yapılıyor...' : 'Giriş yap'}
              <ArrowRight aria-hidden="true" className="ml-1 opacity-80" />
            </Button>
          </form>

          <p className="rise-in rise-3 text-[15px] text-muted-foreground">
            Hesabın yok mu?{' '}
            <Link
              to="/register"
              className="font-semibold text-foreground underline decoration-accent decoration-2 underline-offset-[6px] hover:text-accent transition-colors"
            >
              Kayıt ol
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
