import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError } from '@/api/client'

export function Register() {
  const { registerMutation } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const disabled = !username || !password || !inviteCode

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    registerMutation.mutate({ username, password, invite_code: inviteCode })
  }

  const errorMessage =
    registerMutation.error instanceof ApiError
      ? registerMutation.error.message
      : registerMutation.isError
        ? 'Kayıt başarısız'
        : null

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr] bg-background">
      {/* Editorial aside */}
      <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r border-border/60 bg-card/40 grain px-12 py-14 xl:px-16">
        <div className="relative z-10 flex items-baseline justify-between text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground">
          <span>Anotasyon Platformu</span>
          <span>№ 002</span>
        </div>

        <div className="relative z-10 max-w-xl space-y-7">
          <p className="rise-in rise-1 text-xs font-mono uppercase tracking-[0.22em] text-accent">
            ↳ Yeni bursiyer kaydı
          </p>
          <h1 className="rise-in rise-2 font-display text-5xl xl:text-[3.75rem] font-medium leading-[0.98] tracking-tight text-foreground">
            Anotasyon ekibine
            <br />
            <em className="font-normal italic text-foreground/70">katılma vakti.</em>
          </h1>
          <p className="rise-in rise-3 max-w-md text-base leading-relaxed text-muted-foreground">
            Davet kodunla başla — eğitim adımları seni hazırlayacak, sonra ilk
            özelgenle birlikte gerçek anotasyona geçeceksin.
          </p>
          <ol className="rise-in rise-4 space-y-3 pt-2 text-sm text-muted-foreground">
            <li className="flex items-baseline gap-3">
              <span className="font-mono text-xs text-accent">01.</span>
              Davet kodu doğrulanır.
            </li>
            <li className="flex items-baseline gap-3">
              <span className="font-mono text-xs text-accent">02.</span>
              Kullanım kılavuzu okunur.
            </li>
            <li className="flex items-baseline gap-3">
              <span className="font-mono text-xs text-accent">03.</span>
              Eğitim quizi tamamlanır.
            </li>
            <li className="flex items-baseline gap-3">
              <span className="font-mono text-xs text-accent">04.</span>
              Anotasyona başlanır.
            </li>
          </ol>
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
              Kayıt · Register
            </p>
            <h2 className="font-display text-4xl font-medium leading-tight tracking-tight">
              Yeni hesap
              <br />
              oluştur.
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
                autoComplete="new-password"
                className="h-11 bg-card border-input focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent"
              />
            </div>

            <div className="space-y-2">
              <Label
                htmlFor="invite"
                className="text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground"
              >
                Davet kodu
              </Label>
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                className="h-11 bg-card border-input font-mono tracking-wider focus-visible:ring-1 focus-visible:ring-accent focus-visible:border-accent"
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
              disabled={disabled || registerMutation.isPending}
              className="h-11 w-full bg-primary text-primary-foreground hover:bg-primary/90 transition-all font-medium tracking-wide"
            >
              {registerMutation.isPending ? 'Gönderiliyor…' : 'Kayıt ol'}
              <span className="ml-2 text-primary-foreground/60" aria-hidden>
                →
              </span>
            </Button>
          </form>

          <p className="rise-in rise-3 text-sm text-muted-foreground">
            Zaten hesabın var mı?{' '}
            <Link
              to="/login"
              className="font-medium text-foreground underline decoration-accent decoration-2 underline-offset-[6px] hover:text-accent transition-colors"
            >
              Giriş yap
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
