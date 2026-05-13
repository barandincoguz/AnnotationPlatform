import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

export interface DateRange {
  date_from: string  // YYYY-MM-DD
  date_to: string    // YYYY-MM-DD
}

interface Props {
  value: DateRange | null
  onChange: (v: DateRange | null) => void
}

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function presetRange(days: number): DateRange {
  const now = new Date()
  const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000)
  return { date_from: toISODate(from), date_to: toISODate(now) }
}

export function DateRangePicker({ value, onChange }: Props) {
  const presetValue = (() => {
    if (!value) return 'all'
    return 'custom'  // Custom mode for any explicit range; presets just dispatch onChange
  })()

  return (
    <Select
      value={presetValue}
      onValueChange={(v) => {
        if (v === 'all') onChange(null)
        else if (v === 'd1') onChange(presetRange(1))
        else if (v === 'd7') onChange(presetRange(7))
        else if (v === 'd30') onChange(presetRange(30))
      }}
    >
      <SelectTrigger aria-label="Tarih aralığı">
        <SelectValue placeholder="Tüm zamanlar" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">Tüm zamanlar</SelectItem>
        <SelectItem value="d1">Son 24 saat</SelectItem>
        <SelectItem value="d7">Son 7 gün</SelectItem>
        <SelectItem value="d30">Son 30 gün</SelectItem>
        <SelectItem value="custom" disabled>Özel (yakında)</SelectItem>
      </SelectContent>
    </Select>
  )
}
