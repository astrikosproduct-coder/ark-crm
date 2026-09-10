/**
 * Low Hanging and Top 10 — the two capped, ranked opportunity picks.
 *
 * Single source of truth for the cap sizes, shared by the MSW handler (which
 * enforces it) and the rank-picker control that only ever offers a currently
 * open rank in the first place. Rank is always chosen by the user — never
 * assigned silently — so the handler's job is to validate the choice, not to
 * make it.
 */

type Item = Record<string, unknown>

export interface PriorityFlag {
  flag: string
  rank: string
  cap: number
  label: string
}

export const PRIORITY_FLAGS: readonly PriorityFlag[] = [
  { flag: 'is_low_hanging', rank: 'low_hanging_rank', cap: 5, label: 'Low Hanging' },
  { flag: 'is_top_10', rank: 'top_10_rank', cap: 10, label: 'Top 10' },
]

/** Ranks 1..cap already held by some OTHER record with this flag on. */
export function takenRanksFor(
  allOpportunities: Item[],
  currentId: string,
  flag: string,
  rank: string
): Set<number> {
  const taken = new Set<number>()
  for (const r of allOpportunities) {
    if (r.id === currentId || !r[flag]) continue
    const n = Number(r[rank])
    if (Number.isFinite(n)) taken.add(n)
  }
  return taken
}

/**
 * Resolves one PUT patch against the opportunities collection's priority-flag
 * rules: the chosen rank must be a real, currently open slot, and picking one
 * flag clears the other (Low Hanging and Top 10 are mutually exclusive).
 *
 * Only looks at the flags actually present in `patch` — a save that never
 * touches is_low_hanging or is_top_10 passes through untouched.
 */
export function resolvePriorityFlagPatch(
  allOpportunities: Item[],
  currentId: string,
  current: Item | undefined,
  patch: Item
): { ok: true; patch: Item } | { ok: false; message: string } {
  const out = { ...patch }

  for (const { flag, rank, cap, label } of PRIORITY_FLAGS) {
    if (!(flag in patch)) continue

    const turningOn = Boolean(patch[flag])
    const wasOn = Boolean(current?.[flag])

    if (turningOn) {
      const requested = Number(patch[rank])
      if (!Number.isInteger(requested) || requested < 1 || requested > cap) {
        return { ok: false, message: `Pick a rank between 1 and ${cap} for ${label}.` }
      }

      const taken = takenRanksFor(allOpportunities, currentId, flag, rank)
      if (taken.has(requested)) {
        return {
          ok: false,
          message: `${label} rank ${requested} is already taken — pick another open rank.`,
        }
      }
      out[rank] = requested

      // Mutually exclusive: picking one clears the other.
      for (const other of PRIORITY_FLAGS) {
        if (other.flag === flag) continue
        out[other.flag] = false
        out[other.rank] = null
      }
    } else if (!turningOn && wasOn) {
      out[rank] = null
    }
  }

  return { ok: true, patch: out }
}
