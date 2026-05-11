import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { HelpAccordion } from '@/components/help/HelpAccordion'
import { Button } from '@/components/ui/button'
import { useHelpQuery } from '@/api/queries/help'
import { useSeenManualMutation } from '@/api/queries/me'
import { refreshAuth } from '@/lib/refreshAuth'

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
      <div className="mx-auto max-w-3xl p-6">
        <p className="text-sm text-muted-foreground">Yükleniyor...</p>
      </div>
    )
  }

  if (helpQuery.isError) {
    return (
      <div className="mx-auto max-w-3xl p-6" role="alert">
        <h1 className="text-xl font-semibold">Yardım yüklenemedi</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {helpQuery.error instanceof Error ? helpQuery.error.message : 'Bilinmeyen hata.'}
        </p>
        <Button onClick={() => void helpQuery.refetch()} className="mt-4">
          Tekrar Dene
        </Button>
      </div>
    )
  }

  const sections = helpQuery.data?.sections ?? []

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 ref={h1Ref} tabIndex={-1} className="text-2xl font-semibold focus:outline-none">
        Yardım Kılavuzu
      </h1>
      {firstTime && (
        <p className="mt-2 text-sm text-muted-foreground">
          Lütfen başlamadan önce kılavuzu okuyup eğitime geç.
        </p>
      )}
      <div className="mt-6">
        <HelpAccordion sections={sections} />
      </div>
      {firstTime && (
        <div className="mt-8 flex justify-center">
          <Button
            size="lg"
            onClick={() => void onCtaClick()}
            disabled={seenManualMut.isPending}
          >
            {seenManualMut.isPending ? 'Kaydediliyor...' : 'Anladım, eğitime geç →'}
          </Button>
        </div>
      )}
    </div>
  )
}
