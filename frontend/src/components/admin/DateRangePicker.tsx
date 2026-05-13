import { useState, useRef, useEffect } from 'react'
import { format } from 'date-fns'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

export interface DateRange {
  date_from: string  // YYYY-MM-DD (local TZ)
  date_to: string    // YYYY-MM-DD (local TZ)
}

interface Props {
  value: DateRange | null
  onChange: (v: DateRange | null) => void
}

const PRESET_DAYS = { d1: 1, d7: 7, d30: 30 } as const
type PresetKey = 'all' | keyof typeof PRESET_DAYS

function presetRange(days: number): DateRange {
  const now = new Date()
  const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000)
  return { date_from: format(from, 'yyyy-MM-dd'), date_to: format(now, 'yyyy-MM-dd') }
}

export function DateRangePicker({ value, onChange }: Props) {
  const [preset, setPreset] = useState<PresetKey>('all')
  const prevValue = useRef<DateRange | null>(value)

  // Only sync preset to 'all' when parent transitions value from non-null → null
  // (e.g., an external clear). On the initial render and on intermediate renders
  // where `value` lags behind `preset` (parent hasn't yet propagated onChange),
  // we leave local state alone.
  useEffect(() => {
    if (prevValue.current !== null && value === null && preset !== 'all') {
      setPreset('all')
    }
    prevValue.current = value
  }, [value, preset])

  const handleChange = (next: string) => {
    if (next === 'all') {
      setPreset('all')
      onChange(null)
      return
    }
    if (next === 'd1' || next === 'd7' || next === 'd30') {
      setPreset(next)
      onChange(presetRange(PRESET_DAYS[next]))
    }
  }

  return (
    <Select value={preset} onValueChange={handleChange}>
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
