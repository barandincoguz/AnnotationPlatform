import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import type { Concept } from '@/lib/adminSchemas'

interface Props {
  value: Concept
  onChange: (v: Concept) => void
  onRemove: () => void
}

export function ConceptRowEditor({ value, onChange, onRemove }: Props) {
  const set = (k: keyof Concept, v: string | null) => onChange({ ...value, [k]: v })
  return (
    <div className="flex flex-wrap gap-2 rounded border p-2">
      <Input placeholder="kanun_no (zorunlu)" value={value.kanun_no} onChange={(e) => set('kanun_no', e.target.value)} />
      <Input placeholder="kanun_ad" value={value.kanun_ad ?? ''} onChange={(e) => set('kanun_ad', e.target.value || null)} />
      <Input placeholder="madde" value={value.madde ?? ''} onChange={(e) => set('madde', e.target.value || null)} />
      <Input placeholder="fikra" value={value.fikra ?? ''} onChange={(e) => set('fikra', e.target.value || null)} />
      <Input placeholder="bent" value={value.bent ?? ''} onChange={(e) => set('bent', e.target.value || null)} />
      <Button variant="ghost" size="sm" onClick={onRemove}>Kaldır</Button>
    </div>
  )
}
