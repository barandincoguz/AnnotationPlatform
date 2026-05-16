import { X, Quote } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

interface ReferenceCardProps {
  index: number
  value: ReferenceItem
  onChange: (next: ReferenceItem) => void
  onRemove: () => void
  disabled: boolean
}

function set<K extends keyof ReferenceItem>(prev: ReferenceItem, key: K, v: string): ReferenceItem {
  return { ...prev, [key]: v === '' ? (key === 'source_text' ? '' : null) : v }
}

export function ReferenceCard({ index, value, onChange, onRemove, disabled }: ReferenceCardProps) {
  const id = (k: string) => `ref-${index}-${k}`

  return (
    <Card className="relative overflow-hidden border-border/70 transition-shadow hover:shadow-md">
      {/* Left accent ribbon — a small color seal making the card feel
          like a numbered citation rather than a generic form. */}
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-1 bg-accent2/70"
      />
      <CardContent className="space-y-5 p-5 pl-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-accent2/15 font-mono text-[12px] font-bold text-accent2 tabular-nums">
              {index + 1}
            </span>
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Referans
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={disabled}
            aria-label="sil"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <X />
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-4">
          <div className="space-y-1.5">
            <Label htmlFor={id('kanun_no')}>Kanun No</Label>
            <Input
              id={id('kanun_no')}
              value={value.kanun_no ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_no', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('kanun_ad')}>Kanun Adı</Label>
            <Input
              id={id('kanun_ad')}
              value={value.kanun_ad ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_ad', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('madde')}>Madde</Label>
            <Input
              id={id('madde')}
              value={value.madde ?? ''}
              onChange={(e) => onChange(set(value, 'madde', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('fikra')}>Fıkra</Label>
            <Input
              id={id('fikra')}
              value={value.fikra ?? ''}
              onChange={(e) => onChange(set(value, 'fikra', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor={id('bent')}>Bent</Label>
            <Input
              id={id('bent')}
              value={value.bent ?? ''}
              onChange={(e) => onChange(set(value, 'bent', e.target.value))}
              disabled={disabled}
            />
          </div>
        </div>
        <div className="space-y-1.5 rounded-md border border-accent/20 bg-accent/[0.04] p-3">
          <Label htmlFor={id('source')} className="flex items-center gap-1.5 text-accent">
            <Quote aria-hidden="true" className="h-3 w-3" />
            Metinden Alıntı
          </Label>
          <Textarea
            id={id('source')}
            value={value.source_text}
            onChange={(e) => onChange({ ...value, source_text: e.target.value })}
            disabled={disabled}
            rows={3}
            required
            className="border-accent/30 bg-card focus-visible:border-accent focus-visible:ring-accent"
          />
        </div>
      </CardContent>
    </Card>
  )
}
