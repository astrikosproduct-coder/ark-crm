/**
 * Overall RAG, as a colour.
 *
 * The register's `overall_rag` picklist is Green / Amber / Red — a judgement
 * the owner makes about the pursuit, and the one field on the record whose
 * whole point is to be seen without being read. Everywhere it is drawn it is
 * the SAME mark: a thin solid stripe down the left edge of whatever represents
 * the record — the Kanban card, the list row, the record header. One shape,
 * three places, so a red pursuit looks the same wherever it is met.
 *
 * The colours are the app's existing status tokens, not new hexes: the amber
 * that means "attention" on a stale lead is the same amber that means Amber
 * here. Nothing carries a hex value — see index.css.
 */
const RAG_BORDER: Record<string, string> = {
  GREEN: 'border-l-success',
  AMBER: 'border-l-warning',
  RED: 'border-l-destructive',
}

/** The picklist key a record holds, when it holds a live one. */
export function ragOf(row: Record<string, unknown> | undefined): string | null {
  const value = row?.overall_rag
  if (typeof value !== 'string' || !value) return null
  return value.toUpperCase() in RAG_BORDER ? value.toUpperCase() : null
}

/**
 * The stripe classes for a record, or '' when it has no RAG.
 *
 * A record nobody has rated gets NO stripe rather than a grey one: a fourth
 * colour on the same axis would read as a fourth rating, and "not yet judged"
 * is not a judgement. The absence is the signal.
 */
export function ragAccent(row: Record<string, unknown> | undefined): string {
  const key = ragOf(row)
  return key ? `border-l-4 ${RAG_BORDER[key]}` : ''
}
