import { useState, type FormEvent } from 'react'
import { AlertTriangle, Lightbulb, Send } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { useSubmitFeedbackMutation } from '@/api/queries/feedback'
import type { FeedbackType } from '@/lib/feedbackSchemas'

const OPTIONS: Array<{
  value: FeedbackType
  label: string
  Icon: typeof Lightbulb
  tone: string
}> = [
  { value: 'suggestion', label: 'Öneri', Icon: Lightbulb, tone: 'text-success bg-success/10' },
  { value: 'complaint', label: 'Şikayet', Icon: AlertTriangle, tone: 'text-warning bg-warning/10' },
]

export function Feedback() {
  const [type, setType] = useState<FeedbackType>('suggestion')
  const [message, setMessage] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const submit = useSubmitFeedbackMutation()
  const disabled = message.trim().length === 0 || submit.isPending

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed) return
    submit.mutate(
      { type, message: trimmed },
      {
        onSuccess: () => {
          setMessage('')
          setSubmitted(true)
          toast.success('Geri bildirim kaydedildi')
        },
        onError: () => {
          setSubmitted(false)
          toast.error('Geri bildirim gönderilemedi')
        },
      },
    )
  }

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-4 py-8 sm:px-6">
      <div className="space-y-6">
        <div className="space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Platform · Feedback
          </p>
          <h1 className="font-display text-3xl font-medium tracking-tight">
            Geri Bildirim
          </h1>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-5 rounded-md border border-border/70 bg-card/50 p-4 sm:p-5"
          noValidate
        >
          <div className="space-y-2">
            <Label>Tür</Label>
            <RadioGroup
              value={type}
              onValueChange={(value) => {
                setType(value as FeedbackType)
                setSubmitted(false)
              }}
              className="grid gap-2 sm:grid-cols-2"
            >
              {OPTIONS.map(({ value, label, Icon, tone }) => (
                <Label
                  key={value}
                  htmlFor={`feedback-${value}`}
                  className="flex cursor-pointer items-center gap-3 rounded-md border border-border/70 bg-background px-3 py-3 text-sm transition-colors hover:border-accent/50 has-[[data-state=checked]]:border-accent has-[[data-state=checked]]:bg-accent/5"
                >
                  <RadioGroupItem id={`feedback-${value}`} value={value} aria-label={label} />
                  <span className={`inline-flex h-9 w-9 items-center justify-center rounded-md ${tone}`}>
                    <Icon aria-hidden className="h-4 w-4" />
                  </span>
                  <span className="font-medium">{label}</span>
                </Label>
              ))}
            </RadioGroup>
          </div>

          <div className="space-y-2">
            <Label htmlFor="feedback-message">Mesaj</Label>
            <Textarea
              id="feedback-message"
              value={message}
              onChange={(event) => {
                setMessage(event.target.value)
                setSubmitted(false)
              }}
              rows={7}
              className="min-h-[180px] resize-y bg-background"
            />
          </div>

          {submitted && (
            <p role="status" className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
              Geri bildirim kaydedildi.
            </p>
          )}

          {submit.isError && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Geri bildirim gönderilemedi.
            </p>
          )}

          <div className="flex justify-end">
            <Button type="submit" disabled={disabled}>
              <Send aria-hidden className="h-4 w-4" />
              {submit.isPending ? 'Gönderiliyor...' : 'Gönder'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

