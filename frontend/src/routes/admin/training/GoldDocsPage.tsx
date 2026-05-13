import { useState } from 'react'
import { useAdminGoldDocs } from '@/api/queries/admin'
import { GoldDocEditor } from '@/components/admin/training/GoldDocEditor'

export function GoldDocsPage() {
  const q = useAdminGoldDocs()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = q.data?.resolved.find((d) => d.gold_id === selectedId) ?? null

  if (q.isLoading) return <div>Yükleniyor...</div>
  if (q.isError || !q.data) return <div>Gold doc listesi alınamadı</div>

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[280px_1fr]">
      <aside className="space-y-2">
        <h1 className="text-xl font-semibold">Gold Docs</h1>
        <ul className="space-y-1">
          {q.data.resolved.map((d) => (
            <li key={d.gold_id}>
              <button
                onClick={() => setSelectedId(d.gold_id)}
                className={`block w-full rounded px-3 py-2 text-left text-sm hover:bg-muted ${
                  selectedId === d.gold_id ? 'bg-muted font-medium' : ''
                }`}
              >
                {d.gold_id}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main>
        {selected ? <GoldDocEditor doc={selected} /> : <p className="text-muted-foreground">Soldan bir gold doc seç</p>}
      </main>
    </div>
  )
}
