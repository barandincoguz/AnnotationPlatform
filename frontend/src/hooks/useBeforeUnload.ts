import { useEffect } from 'react'

/**
 * Show the browser's "leave page?" prompt when `enabled` is true.
 *
 * Known limitation: not honored on every mobile browser. Spec §8.5
 * documents that StartScreen warning is the primary user education
 * for "abandoned attempts burn lockout slots".
 */
export function useBeforeUnload(enabled: boolean, message?: string): void {
  useEffect(() => {
    if (!enabled) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = message ?? ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [enabled, message])
}
