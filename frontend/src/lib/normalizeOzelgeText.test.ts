import { describe, it, expect } from 'vitest'
import { normalizeOzelgeText } from './normalizeOzelgeText'

describe('normalizeOzelgeText', () => {
  it('collapses runs of inline spaces to a single space', () => {
    // Sampled from the real DB: "tesis  edildiği,  evinizin  Altuntaş"
    const input = 'tesis  edildiği,   evinizin    Altuntaş'
    expect(normalizeOzelgeText(input)).toBe('tesis edildiği, evinizin Altuntaş')
  })

  it('collapses runs of tabs as well as spaces', () => {
    expect(normalizeOzelgeText('a\t\tb')).toBe('a b')
    expect(normalizeOzelgeText('a \t b')).toBe('a b')
  })

  it('strips trailing horizontal whitespace before newlines', () => {
    expect(normalizeOzelgeText('line one   \nline two')).toBe('line one\nline two')
  })

  it('collapses 3+ consecutive newlines to a single blank line', () => {
    expect(normalizeOzelgeText('p1\n\n\n\np2')).toBe('p1\n\np2')
  })

  it('preserves a single newline (sentence break inside a paragraph)', () => {
    expect(normalizeOzelgeText('line one\nline two')).toBe('line one\nline two')
  })

  it('preserves a paragraph break (exactly one blank line)', () => {
    expect(normalizeOzelgeText('para1\n\npara2')).toBe('para1\n\npara2')
  })

  it('leaves Turkish characters intact', () => {
    const input = 'çağrı  öğrenci  şahane  ğüışçö'
    expect(normalizeOzelgeText(input)).toBe('çağrı öğrenci şahane ğüışçö')
  })

  it('does NOT trim leading whitespace at document start', () => {
    // The header line begins with whitespace on some docs; we don't
    // touch leading edges because that would shift the column layout
    // for PDFs where the title is intentionally indented.
    const input = '   T.C.\nGELİR İDARESİ'
    expect(normalizeOzelgeText(input).startsWith(' T.C.')).toBe(true)
  })

  it('handles empty / nullish input gracefully', () => {
    expect(normalizeOzelgeText('')).toBe('')
  })
})
