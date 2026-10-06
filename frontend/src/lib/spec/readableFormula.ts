import { SpecExprError, tokensOf, type Tok } from './parser'

/**
 * A formula as a person reads it — "ARR × Contract Years + One-Time Revenue"
 * for `arr_annual_recurring * contract_years + one_time_revenue`.
 *
 * WHY IT IS GENERATED (Setup 4e, 5 Oct 2026). The register used to carry a
 * second, hand-written sentence beside every formula, and nothing kept the two
 * in step: edit the formula in Setup and the ⓘ on the record went on describing
 * the old one. Written out from the formula that actually runs, it cannot
 * disagree. Names become labels through `labelOf` — the published register on
 * a record, the draft in Setup — and a name it does not know stays as written.
 *
 * Null when the text is not a formula the language can read: the caller shows
 * nothing rather than something wrong.
 */
const OP_WORDS: Record<string, string> = {
  '*': '×',
  '/': '÷',
  '==': '=',
  '!=': '≠',
  '<=': '≤',
  '>=': '≥',
  '&&': 'and',
  '||': 'or',
  '!': 'not',
  '?': ', then',
  ':': ', otherwise',
}

export function readableFormula(
  expr: string | null | undefined,
  labelOf: (apiName: string) => string | undefined
): string | null {
  if (!expr || !expr.trim()) return null
  let tokens: Tok[]
  try {
    tokens = tokensOf(expr)
  } catch (err) {
    if (err instanceof SpecExprError) return null
    throw err
  }

  const words: string[] = []
  let ternary = false
  for (const tok of tokens) {
    switch (tok.t) {
      case 'end':
        break
      case 'num':
        words.push(String(tok.v))
        break
      case 'str':
        words.push(`“${tok.v}”`)
        break
      case 'ident':
        words.push(labelOf(tok.v) ?? tok.v)
        break
      case 'op':
        if (tok.v === '?') ternary = true
        words.push(OP_WORDS[tok.v] ?? tok.v)
        break
    }
  }

  // Spacing a person expects: none inside brackets, none before a comma.
  const text = words
    .join(' ')
    .replace(/\( /g, '(')
    .replace(/ \)/g, ')')
    .replace(/ ,/g, ',')
    .replace(/\s+/g, ' ')
    .trim()
  return ternary ? `If ${text}` : text
}
