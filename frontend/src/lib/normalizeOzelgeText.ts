/**
 * Conservative whitespace normalizer for özelge PDF text.
 *
 * The backend stores `pdf_text` raw (no cleanup for the PDF path,
 * unlike the htmlText fallback which does run through a normalizer
 * in `backend/documents/parser.py`). The result is a body that
 * faithfully preserves what the PDF extractor produced — including
 * its artifacts: double / triple inline spaces between words,
 * trailing whitespace at end of every line, and ragged blocks of
 * blank lines.
 *
 * This helper applies only safe transforms:
 *   1. Collapse runs of horizontal whitespace (spaces + tabs) to a
 *      single space.
 *   2. Strip trailing horizontal whitespace before any newline.
 *   3. Collapse runs of 3+ consecutive newlines down to 2.
 *
 * It does NOT attempt to repair line-wrapping artifacts (e.g. a
 * heading split across two lines) — those need contextual judgement
 * the regex layer can't safely make. If "aggressive" cleanup ever
 * lands, gate it behind a flag rather than swapping this default.
 */
export function normalizeOzelgeText(input: string): string {
  if (!input) return input
  let s = input
  // 2. Trailing horizontal whitespace BEFORE the newline collapse so
  //    "word   \n   \nword" -> "word\n\nword" rather than leaving the
  //    second line with leading spaces.
  s = s.replace(/[ \t]+(?=\n)/g, '')
  // 1. Multiple horizontal whitespace inside a line -> single space.
  s = s.replace(/[ \t]{2,}/g, ' ')
  // 3. 3+ blank lines (newline runs) -> 2 (one paragraph break).
  s = s.replace(/\n{3,}/g, '\n\n')
  return s
}
