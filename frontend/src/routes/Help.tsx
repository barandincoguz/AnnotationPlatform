import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { HelpAccordion } from '@/components/help/HelpAccordion'
import { Button } from '@/components/ui/button'
import { BrandMark } from '@/components/shell/BrandMark'
import { useHelpQuery } from '@/api/queries/help'
import { useSeenManualMutation } from '@/api/queries/me'
import { refreshAuth } from '@/lib/refreshAuth'

function HelpFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header
        role="banner"
        className="sticky top-0 z-30 h-14 border-b border-border/70 bg-background/85 backdrop-blur-md px-5 flex items-center justify-between"
      >
        <BrandMark subtitle="Yardım · Help" />
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/80 hidden sm:block">
          Kılavuz
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  )
}

export function Help() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const firstTime = searchParams.get('first_time') === 'true'
  const helpQuery = useHelpQuery()
  const seenManualMut = useSeenManualMutation()
  const h1Ref = useRef<HTMLHeadingElement | null>(null)

  useEffect(() => {
    h1Ref.current?.focus()
  }, [])

  const onCtaClick = async () => {
    try {
      await seenManualMut.mutateAsync()
      await refreshAuth(qc)
      navigate('/training', { replace: true })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Bir hata oluştu, tekrar dene.'
      toast.error(message)
    }
  }

  if (helpQuery.isLoading) {
    return (
      <HelpFrame>
        <div className="mx-auto max-w-3xl px-6 py-12">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Yükleniyor...
          </p>
        </div>
      </HelpFrame>
    )
  }

  if (helpQuery.isError) {
    return (
      <HelpFrame>
        <div className="mx-auto max-w-3xl px-6 py-12 space-y-4" role="alert">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-destructive">
            Hata
          </p>
          <h1 className="font-display text-3xl font-medium tracking-tight">
            Yardım yüklenemedi
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {helpQuery.error instanceof Error ? helpQuery.error.message : 'Bilinmeyen hata.'}
          </p>
          <Button onClick={() => void helpQuery.refetch()} className="mt-2">
            Tekrar Dene
            <span aria-hidden className="ml-2 text-primary-foreground/60">↻</span>
          </Button>
        </div>
      </HelpFrame>
    )
  }

  const sections = helpQuery.data?.sections ?? []

  return (
    <HelpFrame>
      <div className="mx-auto max-w-3xl px-6 py-10 lg:py-14">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          {firstTime ? 'Onboarding · Step 01' : 'Kılavuz'}
        </p>
        <h1
          ref={h1Ref}
          tabIndex={-1}
          className="mt-2 font-display text-4xl font-medium tracking-tight focus:outline-none"
        >
          Yardım Kılavuzu
        </h1>
        {firstTime && (
          <div className="mt-4 rounded-md border border-accent/30 bg-accent/5 px-4 py-3">
            <p className="text-sm text-foreground/80 leading-relaxed">
              Lütfen başlamadan önce kılavuzu okuyup eğitime geç.
            </p>
          </div>
        )}
        <div className="mt-8">
          <HelpAccordion sections={sections} />
        </div>
        {firstTime && (
          <div className="mt-10 flex justify-center">
            <Button
              size="lg"
              onClick={() => void onCtaClick()}
              disabled={seenManualMut.isPending}
              className="h-12 bg-primary text-primary-foreground hover:bg-primary/90 font-medium tracking-wide"
            >
              {seenManualMut.isPending ? 'Kaydediliyor...' : 'Anladım, eğitime geç →'}
            </Button>
          </div>
        )}
      </div>
    </HelpFrame>
  )
}
