import { stageNumberOf, stageOf } from '@/lib/pipeline'
import { cn } from '@/lib/utils'

/**
 * A record's stage, read as text.
 *
 * This used to be a per-stage coloured pill — ten hues, one per stage, on a
 * tinted background with a matching border. It is plain text now: a stage is a
 * value like any other field's, and ten tinted boxes in a list column read as
 * decoration rather than as information. Stages 8 and 9 belong to a Deal rather
 * than a Lead, but the same component renders both.
 *
 * Name kept so every caller reads the same — there is nothing chip-like left.
 */
export function StageChip({ value, className }: { value: unknown; className?: string }) {
  const stage = stageNumberOf(value)
  if (stage === null) return <span className="text-muted-foreground">—</span>
  const spec = stageOf(stage)
  return (
    <span className={cn('whitespace-nowrap', className)}>
      {stage} · {spec?.name ?? 'Unknown stage'}
    </span>
  )
}
