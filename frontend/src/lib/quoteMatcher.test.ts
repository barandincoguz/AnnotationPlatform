import { describe, expect, it } from 'vitest'

import { buildSegments, findQuote } from '@/lib/quoteMatcher'

const DOC = [
  'T.C.',
  'GELIR IDARESI BASKANLIGI',
  '',
  'Vergi Usul Kanunu\'nun 114 uncu maddesinde zamanasimi',
  'hukmu duzenlenmistir. Ayrica 114 uncu madde geregince',
  'zamanasimi',
  'hukmu tekrar anilmistir.',
].join('\n')

describe('findQuote', () => {
  it('finds a quote that appears verbatim', () => {
    const match = findQuote(DOC, 'GELIR IDARESI BASKANLIGI')
    expect(match).not.toBeNull()
    expect(DOC.slice(match!.start, match!.end)).toBe('GELIR IDARESI BASKANLIGI')
    expect(match!.mode).toBe('exact')
  })

  it('finds a quote whose newlines were collapsed to spaces by DQCheck', () => {
    // The model stores this as a single line; the document wraps it.
    const match = findQuote(DOC, 'zamanasimi hukmu duzenlenmistir')
    expect(match).not.toBeNull()
    expect(match!.mode).toBe('folded')
    expect(DOC.slice(match!.start, match!.end)).toBe('zamanasimi\nhukmu duzenlenmistir')
  })

  it('tolerates case and typographic punctuation differences', () => {
    const match = findQuote(DOC, 'VERGI USUL KANUNU’NUN 114 UNCU MADDESINDE')
    expect(match).not.toBeNull()
    expect(match!.mode).toBe('folded')
  })

  it('falls back to alphanumeric-only matching', () => {
    const match = findQuote(DOC, 'hukmu, duzenlenmistir!!! ...')
    expect(match).not.toBeNull()
    expect(match!.mode).toBe('loose')
  })

  it('returns null when the quote is absent', () => {
    expect(findQuote(DOC, 'bu cumle dokumanda hic yok')).toBeNull()
  })

  it('returns null for empty input', () => {
    expect(findQuote('', 'x')).toBeNull()
    expect(findQuote(DOC, '   ')).toBeNull()
  })

  it('prefers the occurrence nearest the madde hint when a quote repeats', () => {
    const first = findQuote(DOC, 'zamanasimi hukmu')
    const hinted = findQuote(DOC, 'zamanasimi hukmu', '114 uncu madde geregince')
    expect(first).not.toBeNull()
    expect(hinted).not.toBeNull()
    expect(hinted!.start).toBeGreaterThan(first!.start)
  })

  it('takes the first occurrence when no hint is given', () => {
    const match = findQuote(DOC, 'zamanasimi hukmu')
    expect(match!.start).toBe(DOC.indexOf('zamanasimi'))
  })
})

describe('buildSegments', () => {
  it('reconstructs the original text exactly', () => {
    const segments = buildSegments(DOC, [
      { id: 'a', quote: 'zamanasimi hukmu duzenlenmistir' },
      { id: 'b', quote: 'GELIR IDARESI BASKANLIGI' },
    ])
    expect(segments.map((s) => s.text).join('')).toBe(DOC)
  })

  it('marks each located quote with its id', () => {
    const segments = buildSegments(DOC, [{ id: 'a', quote: 'GELIR IDARESI BASKANLIGI' }])
    const marked = segments.filter((s) => s.quoteId !== null)
    expect(marked).toHaveLength(1)
    expect(marked[0]!.quoteId).toBe('a')
    expect(marked[0]!.text).toBe('GELIR IDARESI BASKANLIGI')
  })

  it('skips quotes it cannot locate without breaking the text', () => {
    const segments = buildSegments(DOC, [{ id: 'ghost', quote: 'yok boyle bir sey' }])
    expect(segments).toHaveLength(1)
    expect(segments[0]!.quoteId).toBeNull()
    expect(segments[0]!.text).toBe(DOC)
  })

  it('keeps the first span when two quotes overlap', () => {
    const segments = buildSegments(DOC, [
      { id: 'outer', quote: 'zamanasimi hukmu duzenlenmistir' },
      { id: 'inner', quote: 'hukmu duzenlenmistir' },
    ])
    expect(segments.map((s) => s.text).join('')).toBe(DOC)
    expect(segments.filter((s) => s.quoteId === 'inner')).toHaveLength(0)
  })
})
