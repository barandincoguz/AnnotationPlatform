import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { client, unwrap } from '@/api/client'
import {
  badgesCatalogSchema, type BadgesCatalog, type BadgeCatalogItem,
} from '@/lib/profileSchemas'
import { useProfile } from '@/api/queries/profile'

export const badgesKeys = {
  all: ['badges'] as const,
  catalog: () => [...badgesKeys.all, 'catalog'] as const,
}

export function useBadgesCatalog() {
  return useQuery<BadgesCatalog>({
    queryKey: badgesKeys.catalog(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/badges/catalog'))
      return badgesCatalogSchema.parse(raw)
    },
    // Catalog is effectively static; never refetch unless invalidated.
    staleTime: Infinity,
  })
}

/** Returns the catalog items the current user has NOT yet earned.
 * Empty array while either query is loading (defensive). */
export function useLockedBadges(): BadgeCatalogItem[] {
  const catalog = useBadgesCatalog()
  const profile = useProfile()
  return useMemo(() => {
    if (!catalog.data || !profile.data) return []
    const earned = new Set(profile.data.badges.map((b) => b.id))
    return catalog.data.filter((c) => !earned.has(c.id))
  }, [catalog.data, profile.data])
}
