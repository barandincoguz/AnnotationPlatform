import { Link } from 'react-router-dom'
import { BrandLogo } from './BrandLogo'

interface BrandMarkProps {
  /** Mono uppercase line under the main title. Optional. */
  subtitle?: string
  /** Override the destination — defaults to home. */
  to?: string
  /** Override the aria-label on the link. */
  ariaLabel?: string
}

/**
 * Editorial brand mark — anchored-crossbar A logo + "Anotasyon Platformu"
 * wordmark + optional mono kicker subtitle. Wrapped in a Link so the
 * mark is always a route-home affordance. Reused by TopBar, AdminLayout,
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
      <BrandLogo className="h-7 w-[2.3rem] text-foreground transition-colors group-hover:text-accent" />
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
