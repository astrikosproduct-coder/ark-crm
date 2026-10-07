import { CheckIcon, TriangleAlertIcon } from 'lucide-react'

import type { Stage } from '@/lib/pipeline'
import { cn } from '@/lib/utils'

export type RailStatus = 'completed' | 'skipped' | 'current' | 'upcoming'

interface Props {
  currentStage: number
  /** Stages some recorded transition jumped clean over AND the record has
   * never been at — see skippedStagesOf in lib/pipeline. A stage below current
   * with no such evidence reads as completed, never skipped: absence of
   * history is not evidence of a skip, and neither is a jump over a stage the
   * record already worked through and moved back from. */
  skipped?: Set<number>
  /** The stages to draw, in order — each module's own stagesFor(module) range. */
  stages: Stage[]
  /** The stage whose fields are on screen, when it is not the current one. */
  viewing?: number
  /** Show a stage's fields. Offered for the current stage and the ones passed. */
  onSelect?: (stage: number) => void
}

function statusOf(stage: number, currentStage: number, skipped: Set<number> | undefined): RailStatus {
  if (stage === currentStage) return 'current'
  if (stage > currentStage) return 'upcoming'
  return skipped?.has(stage) ? 'skipped' : 'completed'
}

const NODE_STYLE: Record<RailStatus, string> = {
  completed: 'border-success bg-success text-white',
  current: 'border-primary bg-primary text-primary-foreground ring-primary/20 ring-4',
  skipped: 'border-warning bg-warning/10 text-warning',
  upcoming: 'border-border bg-background text-muted-foreground',
}

const LINE_STYLE: Record<RailStatus, string> = {
  completed: 'bg-success',
  current: 'bg-border',
  skipped: 'bg-warning/50',
  upcoming: 'bg-border',
}

const LABEL_STYLE: Record<RailStatus, string> = {
  completed: 'text-muted-foreground',
  current: 'text-foreground font-medium',
  skipped: 'text-warning',
  upcoming: 'text-muted-foreground',
}

/**
 * Where this record sits in its module's stage range.
 *
 * A stage the record has PASSED, and the current one, can be clicked to show
 * that stage's fields — without moving the record (6 Oct 2026, Salesforce's
 * Path). Before, the only way to read Stage 5's answers from Stage 6 was to
 * move the record back, which asks for a reason. Upcoming and skipped stages
 * stay plain: the rail was made read-only earlier so that nobody fills in
 * Stage 3's fields on a record still at Stage 1, and that still holds. Moving
 * a record is still the Update Stage dialog's job and only its job.
 *
 * Numbered nodes joined by a line, as it was before the breadcrumb: the number
 * is the stage, the joining line is progress through them. The stage's name is
 * under its node rather than hidden in a tooltip, since with nothing clickable
 * here there is no hover affordance to discover one by.
 */
export function StageRail({ currentStage, skipped, stages, viewing, onSelect }: Props) {
  return (
    <div
      className="flex items-start"
      aria-label={`Stage ${currentStage} of ${stages.length ? stages[stages.length - 1].stage : currentStage}`}
    >
      {stages.map((s, i) => {
        const status = statusOf(s.stage, currentStage, skipped)
        const selectable = Boolean(onSelect) && (status === 'completed' || status === 'current')
        const viewed = viewing === s.stage && viewing !== currentStage
        const Node = selectable ? 'button' : 'div'
        return (
          <div
            key={s.stage}
            className={cn('flex items-start', i < stages.length - 1 && 'min-w-0 flex-1')}
          >
            <Node
              {...(selectable
                ? {
                    type: 'button' as const,
                    onClick: () => onSelect?.(s.stage),
                    title: status === 'current' ? `Show Stage ${s.stage}, where it is now` : `Show Stage ${s.stage}'s fields`,
                    'aria-pressed': viewing === s.stage,
                  }
                : {})}
              className={cn(
                'flex w-16 shrink-0 flex-col items-center gap-1.5',
                selectable && 'group cursor-pointer rounded-md focus-visible:outline-2 focus-visible:outline-offset-2'
              )}
            >
              <span
                className={cn(
                  'flex size-9 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold',
                  NODE_STYLE[status],
                  selectable && 'transition-shadow group-hover:ring-4 group-hover:ring-primary/15',
                  viewed && 'ring-primary/40 ring-4'
                )}
              >
                {status === 'completed' ? (
                  <CheckIcon className="size-4" />
                ) : status === 'skipped' ? (
                  <TriangleAlertIcon className="size-4" />
                ) : (
                  s.stage
                )}
              </span>
              <span
                className={cn(
                  'text-center text-[11px] leading-tight',
                  LABEL_STYLE[status],
                  selectable && 'group-hover:underline group-hover:underline-offset-2',
                  viewed && 'text-foreground font-medium'
                )}
              >
                {s.name}
              </span>
            </Node>
            {/* mt-[17px] centres the joining line on the 36px node above it. */}
            {i < stages.length - 1 && (
              <div className={cn('mt-[17px] h-0.5 min-w-4 flex-1', LINE_STYLE[status])} />
            )}
          </div>
        )
      })}
    </div>
  )
}
