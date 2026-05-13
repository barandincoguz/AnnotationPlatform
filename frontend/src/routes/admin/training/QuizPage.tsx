import { useState } from 'react'
import { useAdminQuiz } from '@/api/queries/admin'
import { QuizEditor } from '@/components/admin/training/QuizEditor'

export function QuizPage() {
  const q = useAdminQuiz()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = q.data?.resolved.find((qq) => qq.id === selectedId) ?? null

  if (q.isLoading) return <div>Yükleniyor...</div>
  if (q.isError || !q.data) return <div>Quiz listesi alınamadı</div>

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[280px_1fr]">
      <aside className="space-y-2">
        <h1 className="text-xl font-semibold">Quiz</h1>
        <ul className="space-y-1">
          {q.data.resolved.map((qq) => (
            <li key={qq.id}>
              <button onClick={() => setSelectedId(qq.id)}
                className={`block w-full rounded px-3 py-2 text-left text-sm hover:bg-muted ${
                  selectedId === qq.id ? 'bg-muted font-medium' : ''
                }`}>
                {qq.id}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main>
        {selected ? <QuizEditor q={selected} /> : <p className="text-muted-foreground">Soldan bir soru seç</p>}
      </main>
    </div>
  )
}
