import { useEffect, useRef, useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BadgeCard } from './BadgeCard'
import { EmptyState } from '@/components/shell/EmptyState'
import { useProfile } from '@/api/queries/profile'
import { useBadgesCatalog } from '@/api/queries/badges'

type TabKey = 'kazanilmis' | 'hepsi'

export function BadgesGrid() {
  const profile = useProfile()
  const catalog = useBadgesCatalog()

  const earned = profile.data?.badges ?? []

  // Codex FRAGILE-E: default tab is "Hepsi" for users with zero earned
  // badges so they see something interesting. Compute the default ONCE
  // when profile data first resolves; never override on later refetches
  // (the user may have switched tabs explicitly).
  const [tab, setTab] = useState<TabKey>('kazanilmis')
  const initializedRef = useRef(false)
  useEffect(() => {
    if (initializedRef.current) return
    if (!profile.data) return
    initializedRef.current = true
    setTab(profile.data.badges.length === 0 ? 'hepsi' : 'kazanilmis')
  }, [profile.data])

  if (catalog.isError) {
    return (
      <section>
        <h2 className="text-lg font-semibold mb-3">Rozetler</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {earned.map((b) => (
            <BadgeCard key={b.id} badge={b} variant="earned" />
          ))}
          {earned.length === 0 && (
            <p className="col-span-full text-sm text-muted-foreground">
              Henüz rozet yok.
            </p>
          )}
        </div>
        <p className="mt-3 text-sm text-warning">
          Tüm rozet kataloğu yüklenemedi.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => { void catalog.refetch() }}
          >
            Yeniden dene
          </button>
        </p>
      </section>
    )
  }

  const catalogItems = catalog.data ?? []

  return (
    <section>
      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Rozetler</h2>
          <TabsList>
            <TabsTrigger value="kazanilmis">Kazanılmış ({earned.length})</TabsTrigger>
            <TabsTrigger value="hepsi">Hepsi ({catalogItems.length})</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="kazanilmis">
          {earned.length === 0 ? (
            <EmptyState
              ornament="☆"
              kicker="Boş"
              title="Henüz rozet yok"
              description="Hepsi sekmesinde mevcut rozetleri gör."
            />
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {earned.map((b) => (
                <BadgeCard key={b.id} badge={b} variant="earned" />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="hepsi">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {catalogItems.map((c) => {
              const earnedRow = earned.find((b) => b.id === c.id)
              if (earnedRow) {
                return <BadgeCard key={c.id} badge={earnedRow} variant="earned" />
              }
              return (
                <BadgeCard
                  key={c.id}
                  badge={{ id: c.id, name: c.name, description: c.description, criterion: c.criterion ?? null }}
                  variant="locked"
                />
              )
            })}
          </div>
        </TabsContent>
      </Tabs>
    </section>
  )
}
