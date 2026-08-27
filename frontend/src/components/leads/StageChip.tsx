import { Badge } from '@/components/ui/badge'
import { stageNumberOf, stageOf } from '@/lib/pipeline'
import { cn } from '@/lib/utils'

/** One colour per stage, 0 to 9, so a Kanban column and a list chip always
 * agree on what a given stage looks like. Index by stage number, not by the
 * picklist key, so a re-sectioned register never breaks the mapping. Stages 8
 * and 9 belong to a Deal rather than a Lead, but the same chip renders both. */
const STAGE_STYLE = [
  'border-slate-500/40 bg-slate-500/10 text-slate-700 dark:text-slate-300',
  'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  'border-cyan-500/40 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300',
  'border-indigo-500/40 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300',
  'border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300',
  'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  'border-teal-500/40 bg-teal-500/10 text-teal-700 dark:text-teal-300',
  'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300',
]

export function StageChip({ value, className }: { value: unknown; className?: string }) {
  const stage = stageNumberOf(value)
  if (stage === null) return <span className="text-muted-foreground">—</span>
  const spec = stageOf(stage)
  return (
    <Badge
      variant="outline"
      className={cn('gap-1 whitespace-nowrap', STAGE_STYLE[stage] ?? STAGE_STYLE[0], className)}
    >
      {stage} · {spec?.name ?? 'Unknown stage'}
    </Badge>
  )
}
