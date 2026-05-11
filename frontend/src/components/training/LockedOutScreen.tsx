import { Button } from '@/components/ui/button'

interface LockedOutScreenProps {
  onLogout: () => void
  onGoToHelp: () => void
}

export function LockedOutScreen({ onLogout, onGoToHelp }: LockedOutScreenProps) {
  return (
    <section role="alert" aria-labelledby="locked-out-heading" className="mx-auto max-w-2xl space-y-4 rounded-md border border-destructive bg-destructive/5 p-6">
      <h2 id="locked-out-heading" className="text-xl font-semibold">Maksimum deneme sayısına ulaşıldı</h2>
      <p className="text-sm">Eğitimi geçemedin. Hesabının sıfırlanması için bir yöneticiyle iletişime geç.</p>
      <p className="text-sm">İletişim: <a href="mailto:team@example.com" className="underline">team@example.com</a></p>
      <div className="flex gap-2">
        <Button onClick={onGoToHelp} variant="outline">Yardımı incele</Button>
        <Button onClick={onLogout} variant="ghost">Çıkış yap</Button>
      </div>
    </section>
  )
}
