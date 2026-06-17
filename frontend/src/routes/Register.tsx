import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BrandLogo } from '@/components/shell/BrandLogo'
import { ApiError } from '@/api/client'

interface Step {
  num: string
  label: string
  /** Tailwind class for the step number tint. */
  tint: string
}

const STEPS: Step[] = [
  { num: '01.', label: 'Davet kodu doğrulanır.', tint: 'text-accent2' },
  { num: '02.', label: 'Kullanım kılavuzu okunur.', tint: 'text-accent' },
  { num: '03.', label: 'Bilgi soruları ve örnek belgeler tamamlanır.', tint: 'text-warning' },
  { num: '04.', label: 'Etiketlemeye başlanır.', tint: 'text-success' },
]

export function Register() {
  const { registerMutation } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const disabled = username.trim().length === 0 || password.length === 0 || inviteCode.trim().length === 0

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    registerMutation.mutate({
      username: username.trim(),
      password,
      invite_code: inviteCode.trim().toUpperCase(),
    })
  }

  const errorMessage =
    registerMutation.error instanceof ApiError
      ? registerMutation.error.message
      : registerMutation.isError
        ? 'Kayıt başarısız'
        : null

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr] bg-background">
      <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r border-border/60 grain px-12 py-14 xl:px-16">
        <div
          aria-hidden
          className="absolute inset-0 -z-10"
          style={{
            background:
              'radial-gradient(at 12% 12%, hsl(175 45% 90% / 0.85) 0px, transparent 55%),' +
              'radial-gradient(at 88% 18%, hsl(32 60% 92% / 0.7) 0px, transparent 50%),' +
              'radial-gradient(at 50% 100%, hsl(145 38% 92% / 0.7) 0px, transparent 60%),' +
              'hsl(var(--card) / 0.6)',
          }}
        />
        <div className="relative z-10 flex items-center justify-between">
          <div className="inline-flex items-center gap-3">
            <BrandLogo className="h-9 w-[2.85rem] text-foreground" />
            <span className="font-display text-[18px] font-bold tracking-tight text-foreground">
              Anotasyon Platformu
            </span>
          </div>
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            002
          </span>
        </div>

        <div className="relative z-10 max-w-xl space-y-8">
          <p className="rise-in rise-1 font-mono text-[12px] font-semibold uppercase tracking-[0.24em] text-accent2">
            Yeni bursiyer kaydı
          </p>
          <h1 className="rise-in rise-2 font-display text-[3.5rem] xl:text-[4.25rem] font-bold leading-[0.95] tracking-tight text-foreground">
            Anotasyon ekibine
            <br />
            <em className="font-medium italic text-accent2">katılma vakti.</em>
          </h1>
          <p className="rise-in rise-3 max-w-md text-[17px] leading-relaxed text-foreground/75">
            Davet kodunla başla. Kılavuz ve eğitim adımları seni hazırlayacak,
            sonra ilk özelgenle birlikte gerçek etiketlemeye geçeceksin.
          </p>
          <ol className="rise-in rise-4 space-y-3 pt-2 text-[16px] text-foreground/80">
            {STEPS.map(({ num, label, tint }) => (
              <li key={num} className="flex items-baseline gap-3">
                <span className={`font-mono text-[13px] font-bold tabular-nums ${tint}`}>
                  {num}
                </span>
                {label}
              </li>
            ))}
          </ol>
        </div>

        <div className="relative z-10 flex items-baseline justify-between font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground/70">
          <span>v0.1.0</span>
          <span>2026 — Murat Karakaya Akademi</span>
        </div>
      </aside>

      <main className="relative flex items-center justify-center overflow-hidden px-6 py-10 sm:px-10 lg:px-14">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 wash-teal"
        />
        <div className="w-full max-w-sm space-y-10">
          <header className="rise-in rise-1 space-y-3">
            <p className="font-mono text-[12px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Kayıt
            </p>
            <h2 className="font-display text-5xl font-bold leading-[1.05] tracking-tight">
              Yeni hesap
              <br />
              oluştur.
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
                autoComplete="new-password"
                className="h-12 bg-card text-base"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="invite">Davet kodu</Label>
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                autoComplete="off"
                spellCheck={false}
                aria-describedby="invite-hint"
                className="h-12 bg-card font-mono text-base tracking-[0.16em]"
              />
              <p id="invite-hint" className="text-xs text-muted-foreground">
                Boşluklar temizlenir, küçük harfler otomatik büyük harfe çevrilir.
              </p>
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
              disabled={disabled || registerMutation.isPending}
              size="lg"
              className="w-full text-base tracking-wide"
            >
              {registerMutation.isPending ? 'Gönderiliyor...' : 'Kayıt ol'}
              <ArrowRight aria-hidden="true" className="ml-1 opacity-80" />
            </Button>
          </form>

          <p className="rise-in rise-3 text-[15px] text-muted-foreground">
            Zaten hesabın var mı?{' '}
            <Link
              to="/login"
              className="font-semibold text-foreground underline decoration-accent decoration-2 underline-offset-[6px] hover:text-accent transition-colors"
            >
              Giriş yap
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
