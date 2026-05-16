import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

interface StartScreenProps {
  onStart: () => void
  onBackToHelp: () => void
  isPending: boolean
}

export function StartScreen({ onStart, onBackToHelp, isPending }: StartScreenProps) {
  const [confirmed, setConfirmed] = useState(false)
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Başlamadan önce
        </p>
        <h2 className="font-display text-2xl font-medium tracking-tight">Eğitim Akışı</h2>
      </div>
      <div className="space-y-2 text-sm">
        <p>Aşağıdaki adımlardan oluşur:</p>
        <ol className="ml-5 list-decimal space-y-1">
          <li>5 soruluk quiz (≥4 doğru)</li>
          <li>3 doküman üzerinde anotasyon (≥2 geçer)</li>
        </ol>
      </div>
      <div className="rounded-md border border-warning/40 bg-warning/5 p-4 text-sm">
        <p className="flex items-center gap-1.5 font-medium">
          <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
          DİKKAT
        </p>
        <p className="mt-1">
          Başladığında <strong>1 deneme harcanır</strong>. Sayfayı yarıda kapatırsan o
          deneme kaybolur ve hak harcanmış sayılır. Maksimum 3 denemen var.
        </p>
      </div>
      <label htmlFor="start-confirm" className="flex items-center gap-2 text-sm cursor-pointer">
        <Checkbox
          id="start-confirm"
          checked={confirmed}
          onCheckedChange={(v) => setConfirmed(v === true)}
        />
        Anladım, başlamaya hazırım
      </label>
      <div className="flex gap-2">
        <Button onClick={onStart} disabled={!confirmed || isPending} size="lg">
          {isPending ? 'Başlatılıyor...' : 'Başla'}
        </Button>
        <Button onClick={onBackToHelp} variant="ghost">← Kılavuza dön</Button>
      </div>
    </div>
  )
}
