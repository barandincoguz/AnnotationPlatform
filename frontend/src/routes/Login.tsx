import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError } from '@/api/client'

export function Login() {
  const { loginMutation } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const disabled = username.length === 0 || password.length === 0

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    loginMutation.mutate({ username, password }, { onSuccess: () => navigate('/') })
  }

  const errorMessage =
    loginMutation.error instanceof ApiError
      ? loginMutation.error.message
      : loginMutation.isError
        ? 'Giriş yapılamadı'
        : null

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr] bg-background">
      {/* Editorial aside */}
      <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r border-border/60 bg-card/40 grain px-12 py-14 xl:px-16">
        <div className="relative z-10 flex items-baseline justify-between text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground">
          <span>Anotasyon Platformu</span>
          <span>№ 001</span>
        </div>

        <div className="relative z-10 max-w-xl space-y-7">
          <p className="rise-in rise-1 text-xs font-mono uppercase tracking-[0.22em] text-accent">
            ↳ Bursiyer girişi
          </p>
          <h1 className="rise-in rise-2 font-display text-5xl xl:text-[3.75rem] font-medium leading-[0.98] tracking-tight text-foreground">
            Türk vergi hukukuna
            <br />
            <em className="font-normal italic text-foreground/70">titiz bir bakış.</em>
          </h1>
          <p className="rise-in rise-3 max-w-md text-base leading-relaxed text-muted-foreground">
            Özelgelerden kanun atıfı çıkarımı — bursiyer ekibinin titizlikle hazırladığı,
            vergi pratisyenleri için bir referans kütüphanesi.
          </p>
          <div className="rise-in rise-4 flex items-center gap-4 pt-2 text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground/80">
            <span>17.923 özelge</span>
            <span className="h-px w-6 bg-border" aria-hidden />
            <span>kanun atıfı çıkarımı</span>
          </div>
        </div>

        <div className="relative z-10 flex items-baseline justify-between text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground/70">
          <span>v0.1.0</span>
          <span>2026 — Murat Karakaya Akademi</span>
        </div>
      </aside>

      {/* Form panel */}
      <main className="flex items-center justify-center px-6 py-10 sm:px-10 lg:px-14">
        <div className="w-full max-w-sm space-y-10">
          <header className="rise-in rise-1 space-y-3">
            <p className="text-xs font-mono uppercase tracking-[0.22em] text-muted-foreground">
              Giriş · Login
            </p>
            <h2 className="font-display text-4xl font-medium leading-tight tracking-tight">
              Tekrar
              <br />
              hoş geldin.
            </h2>
          </header>

          <form onSubmit={handleSubmit} className="rise-in rise-2 space-y-5" noValidate>
            <div className="space-y-2">
              <Label
                htmlFor="username"
                className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground"
              >
                Kullanıcı adı
              </Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="h-11 bg-card border-input focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent"
              />
            </div>

            <div className="space-y-2">
              <Label
                htmlFor="password"
                className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground"
              >
                Şifre
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="h-11 bg-card border-input focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent"
              />
            </div>

            {errorMessage && (
              <p
                className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
                role="alert"
              >
                {errorMessage}
              </p>
            )}

            <Button
              type="submit"
              disabled={disabled || loginMutation.isPending}
              className="h-11 w-full bg-primary text-primary-foreground hover:bg-primary/90 transition-all font-medium tracking-wide"
            >
              {loginMutation.isPending ? 'Giriş yapılıyor…' : 'Giriş yap'}
              <span className="ml-2 text-primary-foreground/60" aria-hidden>
                →
              </span>
            </Button>
          </form>

          <p className="rise-in rise-3 text-sm text-muted-foreground">
            Hesabın yok mu?{' '}
            <Link
              to="/register"
              className="font-medium text-foreground underline decoration-accent decoration-2 underline-offset-[6px] hover:text-accent transition-colors"
            >
              Kayıt ol
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
