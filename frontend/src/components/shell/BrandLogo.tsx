/**
 * Brand mark — "Anchored Crossbar A".
 *
 * Geometric capital A with serif feet, a horizontal crossbar that exits
 * the right leg and extends into a citation rule (semantic: legal
 * annotation / underlined reference), and a single accent dot above the
 * rule as an authority seal.
 *
 * Currentcolor drives the outline, so the mark inherits the surrounding
 * text colour; the accent dot is the sole intrinsic colour and uses
 * hsl(var(--accent)) so it follows theme refreshes automatically.
 */
interface BrandLogoProps {
  className?: string
}

export function BrandLogo({ className }: BrandLogoProps) {
  return (
    <svg
      viewBox="0 0 44 32"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      {/* A glyph with serif feet */}
      <path
        d="M2 28 L6 28 M4 28 L14 4 L24 28 M22 28 L26 28"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      {/* Crossbar that exits the right leg and runs out as a citation rule */}
      <path
        d="M9 21 L40 21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="square"
      />
      {/* Accent dot — authority seal mark */}
      <circle cx="36" cy="14" r="1.8" fill="hsl(var(--accent))" />
    </svg>
  )
}
