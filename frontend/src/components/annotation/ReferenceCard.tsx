import { X } from 'lucide-react'
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
    <Card>
      <CardContent className="space-y-2 p-3">
        <div className="flex items-start justify-between">
          <span className="text-xs font-medium text-muted-foreground">Referans #{index + 1}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={disabled}
            aria-label="sil"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor={id('kanun_no')}>kanun_no</Label>
            <Input
              id={id('kanun_no')}
              value={value.kanun_no ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_no', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={id('kanun_ad')}>kanun_ad</Label>
            <Input
              id={id('kanun_ad')}
              value={value.kanun_ad ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_ad', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={id('madde')}>madde</Label>
            <Input
              id={id('madde')}
              value={value.madde ?? ''}
              onChange={(e) => onChange(set(value, 'madde', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={id('fikra')}>fıkra</Label>
            <Input
              id={id('fikra')}
              value={value.fikra ?? ''}
              onChange={(e) => onChange(set(value, 'fikra', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1 col-span-2">
            <Label htmlFor={id('bent')}>bent</Label>
            <Input
              id={id('bent')}
              value={value.bent ?? ''}
              onChange={(e) => onChange(set(value, 'bent', e.target.value))}
              disabled={disabled}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor={id('source')}>source_text</Label>
          <Textarea
            id={id('source')}
            value={value.source_text}
            onChange={(e) => onChange({ ...value, source_text: e.target.value })}
            disabled={disabled}
            rows={3}
            required
          />
        </div>
      </CardContent>
    </Card>
  )
}
