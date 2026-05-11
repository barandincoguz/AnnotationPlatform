import { useState } from 'react'
import { Button } from '@/components/ui/button'

interface StartScreenProps {
  onStart: () => void
  onBackToHelp: () => void
  isPending: boolean
}

export function StartScreen({ onStart, onBackToHelp, isPending }: StartScreenProps) {
  const [confirmed, setConfirmed] = useState(false)
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2 text-sm">
        <p>Aşağıdaki adımlardan oluşur:</p>
        <ol className="ml-5 list-decimal space-y-1">
          <li>5 soruluk quiz (≥4 doğru)</li>
          <li>3 doküman üzerinde anotasyon (≥2 geçer)</li>
        </ol>
      </div>
      <div className="rounded-md border border-amber-500/50 bg-amber-50 p-4 text-sm dark:bg-amber-950/20">
        <p className="font-medium">⚠ DİKKAT</p>
        <p className="mt-1">
          Başladığında <strong>1 deneme harcanır</strong>. Sayfayı yarıda kapatırsan o
          deneme kaybolur ve hak harcanmış sayılır. Maksimum 3 denemen var.
        </p>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          className="h-4 w-4"
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
