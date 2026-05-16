import { Link } from 'react-router-dom'

interface BrandMarkProps {
  /** Mono uppercase line under the main title. Optional. */
  subtitle?: string
  /** Override the destination — defaults to home. */
  to?: string
  /** Override the aria-label on the link. */
  ariaLabel?: string
}

/**
 * Editorial brand mark — Fraunces "A" monogram + "Anotasyon Platformu"
 * wordmark + optional mono kicker subtitle. Wrapped in a Link so the
 * mark is always a route home affordance. Reused by TopBar, AdminLayout,
 * and standalone authed pages (Help) so users never need to fall back
 * to the URL bar.
 */
export function BrandMark({
  subtitle,
  to = '/',
  ariaLabel = 'Anotasyon ana sayfasına dön',
}: BrandMarkProps) {
  return (
    <Link
      to={to}
      aria-label={ariaLabel}
      className="group inline-flex items-center gap-3 outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md transition-opacity w-fit"
    >
      <span
        aria-hidden
        className="grid h-8 w-8 place-items-center rounded-md border border-border bg-card font-display text-base font-semibold text-foreground transition-colors group-hover:border-accent group-hover:text-accent"
      >
        A
      </span>
      <span className="flex flex-col leading-tight">
        <span className="font-display text-[15px] font-semibold tracking-tight text-foreground">
          Anotasyon Platformu
        </span>
        {subtitle && (
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {subtitle}
          </span>
        )}
      </span>
    </Link>
  )
}
