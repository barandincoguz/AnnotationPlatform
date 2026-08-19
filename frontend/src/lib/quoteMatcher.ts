/**
 * Locate a model-proposed quote inside the document text the viewer renders.
 *
 * Why not `text.indexOf(quote)`: DQCheck normalizes its `source_text` with
 * `normalize_text`, which collapses EVERY whitespace run — newlines included —
 * into single spaces. `DocViewer` renders `normalizeOzelgeText(pdf_text)`, which
 * preserves newlines. PDF-extracted özelge text wraps about every 80 characters,
 * so most quotes straddle a line break and a plain substring search fails.
 *
 * Three escalating levels are tried in order: `exact` (verbatim), `folded`
 * (whitespace collapsed, typographic punctuation normalized, lowercased) and
 * `loose` (folded plus every non-alphanumeric character dropped). Each level
 * keeps an index map back to original offsets, so the caller always gets
 * coordinates into the string it rendered.
 *
 * When a level yields several matches the one closest to `near` — normally the
 * reference's `madde` token — wins; with no usable hint the first match wins.
 */

export type QuoteMatchMode = 'exact' | 'folded' | 'loose'

export interface QuoteMatch {
  start: number
  end: number
  mode: QuoteMatchMode
}

export interface QuoteTarget {
  id: string
  quote: string
  near?: string
}

export interface QuoteSegment {
  text: string
  quoteId: string | null
}

interface Projection {
  text: string
  map: number[]
}

const PUNCTUATION: Record<string, string> = {
  '“': '"',
  '”': '"',
  '‘': "'",
  '’': "'",
  '–': '-',
  '—': '-',
}

// Mirrors data_quality_checker.text._LOOSE_RE (Turkish lowercase alphabet).
const ALPHANUMERIC = /[0-9a-zçğıöşü]/

function identity(input: string): Projection {
  return { text: input, map: Array.from(input, (_char, index) => index) }
}

function fold(input: string, { loose }: { loose: boolean }): Projection {
  const chars: string[] = []
  const map: number[] = []
  let pendingSpace = false
  for (let index = 0; index < input.length; index += 1) {
    const original = input[index] as string
    const substituted = PUNCTUATION[original] ?? original
    // `toLowerCase` (not the tr locale) mirrors Python's str.casefold, which
    // maps "I" to "i" — locale-aware lowering would produce "ı" and stop
    // matching DQCheck's folded text.
    const lowered = substituted.toLowerCase()
    const isSpace = /\s/.test(substituted)
    const dropped = loose && !isSpace && !ALPHANUMERIC.test(lowered)
    if (isSpace || dropped) {
      pendingSpace = chars.length > 0
      continue
    }
    if (pendingSpace) {
      chars.push(' ')
      map.push(index)
      pendingSpace = false
    }
    // A single source char can lower into several code units ("İ" → "i̇"); each
    // unit maps back to the same original offset so map and text stay aligned.
    for (const unit of lowered) {
      chars.push(unit)
      map.push(index)
    }
  }
  return { text: chars.join(''), map }
}

const LEVELS: Array<{ mode: QuoteMatchMode; project: (input: string) => Projection }> = [
  { mode: 'exact', project: identity },
  { mode: 'folded', project: (input) => fold(input, { loose: false }) },
  { mode: 'loose', project: (input) => fold(input, { loose: true }) },
]

function occurrences(haystack: string, needle: string): number[] {
  const found: number[] = []
  if (!needle) return found
  let from = 0
  for (;;) {
    const index = haystack.indexOf(needle, from)
    if (index < 0) return found
    found.push(index)
    from = index + 1
  }
}

function pickNearest(candidates: number[], projected: string, hint: string): number {
  const first = candidates[0] as number
  if (candidates.length === 1 || !hint) return first
  const hintPositions = occurrences(projected, hint)
  if (hintPositions.length === 0) return first
  let best = first
  let bestDistance = Number.POSITIVE_INFINITY
  for (const candidate of candidates) {
    for (const hintPosition of hintPositions) {
      const distance = Math.abs(candidate - hintPosition)
      if (distance < bestDistance) {
        bestDistance = distance
        best = candidate
      }
    }
  }
  return best
}

export function findQuote(haystack: string, quote: string, near?: string): QuoteMatch | null {
  const trimmed = quote.trim()
  if (!haystack || !trimmed) return null

  for (const level of LEVELS) {
    const projection = level.project(haystack)
    const needle = level.project(trimmed).text
    if (!needle) continue
    const candidates = occurrences(projection.text, needle)
    if (candidates.length === 0) continue
    const hint = near ? level.project(near).text : ''
    const start = pickNearest(candidates, projection.text, hint)
    const startOriginal = projection.map[start] as number
    const endOriginal = (projection.map[start + needle.length - 1] as number) + 1
    return { start: startOriginal, end: endOriginal, mode: level.mode }
  }
  return null
}

export function buildSegments(text: string, targets: QuoteTarget[]): QuoteSegment[] {
  const spans: Array<{ start: number; end: number; id: string }> = []
  for (const target of targets) {
    const match = findQuote(text, target.quote, target.near)
    if (match) spans.push({ start: match.start, end: match.end, id: target.id })
  }
  spans.sort((left, right) => left.start - right.start || right.end - left.end)

  const segments: QuoteSegment[] = []
  let cursor = 0
  for (const span of spans) {
    if (span.start < cursor) continue // overlapping span: the first one wins
    if (span.start > cursor) {
      segments.push({ text: text.slice(cursor, span.start), quoteId: null })
    }
    segments.push({ text: text.slice(span.start, span.end), quoteId: span.id })
    cursor = span.end
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), quoteId: null })
  }
  return segments
}
