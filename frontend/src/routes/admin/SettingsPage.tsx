import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useSettings, useUpdateSettingMutation } from '@/api/queries/admin'
import type { SettingValue } from '@/lib/adminSchemas'

function groupByPrefix(map: Record<string, SettingValue>): Record<string, [string, SettingValue][]> {
  const groups: Record<string, [string, SettingValue][]> = {}
  for (const [k, v] of Object.entries(map)) {
    const prefix = k.split('.')[0] ?? k
    groups[prefix] ??= []
    groups[prefix].push([k, v])
  }
  for (const g of Object.values(groups)) g.sort(([a], [b]) => a.localeCompare(b))
  return groups
}

interface CardProps {
  k: string
  serverValue: SettingValue
}

function SettingCard({ k, serverValue }: CardProps) {
  const [draft, setDraft] = useState<SettingValue>(serverValue)
  useEffect(() => { setDraft(serverValue) }, [serverValue])
  const dirty = draft !== serverValue
  const upd = useUpdateSettingMutation()

  const onSave = () => {
    upd.mutate({ key: k, value: draft }, {
      onSuccess: () => toast.success(`${k} güncellendi`),
      onError: (err: unknown) => {
        const status = (err as { status?: number })?.status
        toast.error(status === 422 ? 'Değer tipi uyumsuz' : 'Kaydedilemedi')
      },
    })
  }

  return (
    <div className="rounded border p-3 space-y-2">
      <div className="font-mono text-sm">{k}</div>
      {typeof serverValue === 'boolean' && (
        <Switch checked={draft === true} onCheckedChange={(v) => setDraft(v)} />
      )}
      {typeof serverValue === 'number' && (
        <Input type="number" value={String(draft)} onChange={(e) => setDraft(Number(e.target.value))} />
      )}
      {typeof serverValue === 'string' && (
        <Input value={String(draft)} onChange={(e) => setDraft(e.target.value)} />
      )}
      {!['boolean', 'number', 'string'].includes(typeof serverValue) && (
        <div className="text-xs text-muted-foreground">Bu ayar tipi UI&apos;dan düzenlenemez</div>
      )}
      <div className="flex gap-2">
        <Button size="sm" disabled={!dirty || upd.isPending} onClick={onSave}>Kaydet</Button>
        <Button size="sm" variant="ghost" disabled={!dirty} onClick={() => setDraft(serverValue)}>Geri Al</Button>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const q = useSettings()
  if (q.isLoading) return <div>Yükleniyor...</div>
  if (q.isError || !q.data) return <div>Ayarlar alınamadı</div>
  const grouped = groupByPrefix(q.data)
  const prefixes = Object.keys(grouped)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Runtime Settings</h1>
      {prefixes.map((p) => (
        <section key={p} className="space-y-2">
          <h2 className="text-lg font-medium">{p}</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(grouped[p] ?? []).map(([k, v]) => (
              <SettingCard key={k} k={k} serverValue={v} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
