import { useEffect, useMemo, useState } from 'react'

import { allChecksOf, attestationsNeeded } from '@/lib/readiness'
import type { Values } from '@/lib/spec/conditions'

/**
 * The ticks for one Update Stage dialog. A FORWARD move (including a skip)
 * waits until every manual check is ticked; a move back does not, because the
 * record is returning to a stage it already met. Ticks reset when the target
 * stage changes — a check ticked for Stage 4 says nothing about Stage 6.
 */
export function useAttestations(module: string, values: Values, from: number, to: number) {
  const [attested, setAttested] = useState<ReadonlySet<string>>(new Set())
  useEffect(() => setAttested(new Set()), [to])

  const needed = useMemo(() => attestationsNeeded(module, values, from, to), [module, values, from, to])
  // Every check on screen, so a criterion the RECORD cannot settle can still be
  // ticked by the person and recorded. Only the manual ones block the move.
  const all = useMemo(() => allChecksOf(module, values, from, to), [module, values, from, to])
  const outstanding = to > from ? needed.filter((item) => !attested.has(item.key)) : []

  return {
    attested,
    toggle: (key: string) =>
      setAttested((current) => {
        const next = new Set(current)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      }),
    outstanding,
    /**
     * What the transition records — only checks actually shown and ticked,
     * including a criterion the person ticked against what the record reads.
     */
    codes: all.filter((item) => attested.has(item.key)).map((item) => item.code ?? item.key),
  }
}
