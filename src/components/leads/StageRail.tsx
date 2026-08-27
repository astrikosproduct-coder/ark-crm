import { CheckIcon, TriangleAlertIcon } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Stage } from '@/lib/pipeline'
import { cn } from '@/lib/utils'

export type RailStatus = 'completed' | 'skipped' | 'current' | 'upcoming'

interface Props {
  currentStage: number
  selectedStage: number
  /** Stages some recorded transition jumped clean over — see
   * skippedStagesOf in lib/pipeline. A stage below current with no such
   * evidence reads as completed, never skipped: absence of history is not
   * evidence of a skip. */
  skipped?: Set<number>
  onSelectStage: (stage: number) => void
  /** The stages to draw, in order — each module's own stagesFor(module) range. */
  stages: Stage[]
}

function statusOf(stage: number, currentStage: number, skipped: Set<number> | undefined): RailStatus {
  if (stage === currentStage) return 'current'
  if (stage > currentStage) return 'upcoming'
  return skipped?.has(stage) ? 'skipped' : 'completed'
}

const NODE_STYLE: Record<RailStatus, string> = {
  completed: 'border-emerald-500 bg-emerald-500 text-white',
  current: 'border-primary bg-primary text-primary-foreground ring-4 ring-primary/20',
  skipped: 'border-amber-500 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  upcoming: 'border-border bg-background text-muted-foreground',
}

const LINE_STYLE: Record<RailStatus, string> = {
  completed: 'bg-emerald-500',
  current: 'bg-border',
  skipped: 'bg-amber-500/50',
  upcoming: 'bg-border',
}

/**
 * Horizontal stage rail, drawn over whichever range the caller's module owns.
 * Every node is clickable, whatever its status — reviewing a skipped or
 * upcoming stage's fields is exactly what "clicking a stage shows that
 * stage's fields" means in the prompt.
 */
export function StageRail({ currentStage, selectedStage, skipped, onSelectStage, stages }: Props) {
  return (
    <div className="flex items-center">
      {stages.map((s, i) => {
        const status = statusOf(s.stage, currentStage, skipped)
        const selected = s.stage === selectedStage
        return (
          <div key={s.stage} className={cn('flex items-center', i < stages.length - 1 && 'flex-1')}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => onSelectStage(s.stage)}
                  className={cn(
                    'flex size-9 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors',
                    NODE_STYLE[status],
                    selected && status !== 'current' && 'outline outline-2 outline-offset-2 outline-primary'
                  )}
                >
                  {status === 'completed' ? (
                    <CheckIcon className="size-4" />
                  ) : status === 'skipped' ? (
                    <TriangleAlertIcon className="size-4" />
                  ) : (
                    s.stage
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="font-medium">
                  Stage {s.stage} · {s.name}
                </p>
                <p className="text-muted-foreground">
                  {status === 'skipped' ? 'Skipped — no record of this stage in History' : status}
                </p>
              </TooltipContent>
            </Tooltip>
            {i < stages.length - 1 && <div className={cn('h-0.5 flex-1', LINE_STYLE[status])} />}
          </div>
        )
      })}
    </div>
  )
}
