import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/authStore'
import { useTrainingStore } from '@/stores/trainingStore'
import { useBeforeUnload } from '@/hooks/useBeforeUnload'
import {
  useTrainingStartMutation,
  useQuizSubmitMutation,
  useAnnotateSubmitMutation,
  PENDING_START_SENTINEL_KEY,
} from '@/api/queries/training'
import { useLogoutMutation } from '@/api/queries/auth'
import { refreshAuth } from '@/lib/refreshAuth'
import { submitWithRecovery, AbortAdvance } from '@/lib/trainingRecovery'
import { is403LockedOut, is409AlreadyPassed } from '@/lib/apiError'
import { TrainingProgress } from '@/components/training/TrainingProgress'
import { StartScreen } from '@/components/training/StartScreen'
import { QuizStep } from '@/components/training/QuizStep'
import { AnnotateStep } from '@/components/training/AnnotateStep'
import { SummaryStep } from '@/components/training/SummaryStep'
import { LockedOutScreen } from '@/components/training/LockedOutScreen'
import { PendingStartBanner } from '@/components/training/PendingStartBanner'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export function Training() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const step = useTrainingStore((s) => s.step)
  const docIndex = useTrainingStore((s) => s.docIndex)
  const attemptId = useTrainingStore((s) => s.attemptId)
  const hydrate = useTrainingStore((s) => s.hydrate)
  const recordQuizResult = useTrainingStore((s) => s.recordQuizResult)
  const recordDocResult = useTrainingStore((s) => s.recordDocResult)
  const advanceDoc = useTrainingStore((s) => s.advanceDoc)
  const setStep = useTrainingStore((s) => s.setStep)
  const clear = useTrainingStore((s) => s.clear)

  const startMut = useTrainingStartMutation()
  const quizMut = useQuizSubmitMutation()
  const annMut = useAnnotateSubmitMutation()
  const logoutMut = useLogoutMutation()

  const [pendingSentinelVisible, setPendingSentinelVisible] = useState(false)

  useEffect(() => {
    if (user?.has_passed_training && step !== 'summary' && step !== 'locked-out') {
      navigate('/', { replace: true })
    }
  }, [user, step, navigate])

  useEffect(() => {
    if (step === 'idle' && sessionStorage.getItem(PENDING_START_SENTINEL_KEY)) {
      setPendingSentinelVisible(true)
    }
  }, [step])

  useBeforeUnload(
    (step === 'quiz' || step === 'doc') && !quizMut.isPending && !annMut.isPending,
    'Eğitime devam ediyorsun, sayfayı kapatma.',
  )

  const handleStart = async () => {
    try {
      const startResp = await startMut.mutateAsync()
      hydrate(startResp)
      sessionStorage.removeItem(PENDING_START_SENTINEL_KEY)
      setPendingSentinelVisible(false)
    } catch (err) {
      if (is409AlreadyPassed(err)) {
        sessionStorage.removeItem(PENDING_START_SENTINEL_KEY)
        setPendingSentinelVisible(false)
        await refreshAuth(qc)
        navigate('/', { replace: true })
        return
      }
      if (is403LockedOut(err)) {
        sessionStorage.removeItem(PENDING_START_SENTINEL_KEY)
        setPendingSentinelVisible(false)
        setStep('locked-out')
        return
      }
      toast.error('Eğitim başlatılamadı, tekrar dene.')
    }
  }

  const handleQuizSubmit = async (answers: Record<string, number>) => {
    if (attemptId === null) return
    try {
      const result = await submitWithRecovery({
        submit: () => quizMut.mutateAsync({ attempt_id: attemptId, answers }),
        key: { kind: 'quiz' },
        qc,
      })
      recordQuizResult(result)
    } catch (err) {
      if (err instanceof AbortAdvance) return
      toast.error('Cevap gönderilemedi, tekrar dene.')
    }
  }

  const handleDocSubmit = async (goldId: string, references: ReferenceItem[]) => {
    if (attemptId === null) return
    try {
      const result = await submitWithRecovery({
        submit: () => annMut.mutateAsync({ attempt_id: attemptId, gold_id: goldId, references }),
        key: { kind: 'doc', goldId },
        qc,
      })
      recordDocResult(goldId, result)
    } catch (err) {
      if (err instanceof AbortAdvance) return
      toast.error('Anotasyon gönderilemedi, tekrar dene.')
    }
  }

  const handleDocAdvance = async () => {
    if (docIndex < 2) {
      advanceDoc()
      return
    }
    // Set step to 'summary' BEFORE refreshAuth so the redirect guard
    // (which fires on has_passed_training flip) sees step='summary'
    // and does not navigate away.
    setStep('summary')
    try {
      await refreshAuth(qc)
    } catch {
      useTrainingStore.setState({ degraded: true })
    }
  }

  const handleRetry = async () => {
    clear()
    await handleStart()
  }

  const handleLogout = () => {
    clear()
    logoutMut.mutate()
  }

  const handleGoHelp = () => navigate('/help', { replace: false })
  const handleAnnotate = () => {
    clear()
    navigate('/', { replace: true })
  }
  const handleDismissPending = () => {
    sessionStorage.removeItem(PENDING_START_SENTINEL_KEY)
    setPendingSentinelVisible(false)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-6 py-10 lg:py-14">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
        Eğitim
      </p>
      <h1 className="mb-6 font-display text-4xl font-medium tracking-tight">Eğitim</h1>
      {pendingSentinelVisible && step === 'idle' && (
        <div className="mb-6">
          <PendingStartBanner onDismiss={handleDismissPending} onStartNew={() => void handleStart()} />
        </div>
      )}
      {step !== 'idle' && step !== 'locked-out' && (
        <TrainingProgress step={step} docIndex={docIndex} />
      )}
      {step === 'idle' && (
        <StartScreen onStart={() => void handleStart()} onBackToHelp={handleGoHelp} isPending={startMut.isPending} />
      )}
      {step === 'quiz' && (
        <QuizStep onSubmit={(answers) => void handleQuizSubmit(answers)} isSubmitting={quizMut.isPending} />
      )}
      {step === 'doc' && (
        <AnnotateStep
          onSubmit={(goldId, refs) => void handleDocSubmit(goldId, refs)}
          onAdvance={() => void handleDocAdvance()}
          isSubmitting={annMut.isPending}
        />
      )}
      {step === 'summary' && (
        <SummaryStep
          onAnnotate={handleAnnotate}
          onRetry={() => void handleRetry()}
          onBackToHelp={handleGoHelp}
        />
      )}
      {step === 'locked-out' && (
        <LockedOutScreen onLogout={handleLogout} onGoToHelp={handleGoHelp} />
      )}
      </div>
    </div>
  )
}
