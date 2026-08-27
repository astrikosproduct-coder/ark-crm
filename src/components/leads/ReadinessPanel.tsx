import { CheckIcon, TriangleAlertIcon, XIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { computeReadiness, layerCounts, type ReadinessItem } from '@/lib/readiness'
import type { Values } from '@/lib/spec/conditions'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

interface Props {
  module: string
  values: Values
  from: number
  to: number
  onJumpToField?: (field: FieldSpec) => void
  className?: string
}

const ICON = {
  pass: <CheckIcon className="size-3.5 text-emerald-600 dark:text-emerald-400" />,
  fail: <XIcon className="size-3.5 text-rose-600 dark:text-rose-400" />,
  warn: <TriangleAlertIcon className="size-3.5 text-amber-600 dark:text-amber-400" />,
}

function Item({ item, onJumpToField }: { item: ReadinessItem; onJumpToField?: (field: FieldSpec) => void }) {
  return (
    <li className="flex items-start gap-2 py-1 text-sm">
      <span className="mt-0.5 shrink-0">{ICON[item.status]}</span>
      <span className="min-w-0 flex-1">
        <span className={cn(item.status === 'fail' && 'text-foreground')}>
          {item.code && <span className="text-muted-foreground">{item.code} · </span>}
          {item.label}
        </span>
        {item.detail && <span className="block text-xs text-muted-foreground">{item.detail}</span>}
        {item.field && onJumpToField && (
          <button
            type="button"
            className="block text-xs text-primary underline underline-offset-2"
            onClick={() => onJumpToField(item.field as FieldSpec)}
          >
            Go to {item.field.label}
          </button>
        )}
      </span>
    </li>
  )
}

/**
 * Always-visible right column on the Lead detail page. Advisory only — see
 * CLAUDE.md POC-1 note: it shows what would block a real transition check, but
 * the Advance button works regardless of what's shown here.
 */
export function ReadinessPanel({ module, values, from, to, onJumpToField, className }: Props) {
  const readiness = computeReadiness(module, values, from, to)

  return (
    <div className={cn('space-y-4 rounded-lg border p-4', className)}>
      <div>
        <h2 className="text-sm font-semibold">Readiness panel</h2>
        <p className="text-xs text-muted-foreground">
          Stage {from} → Stage {to}. Advisory only — nothing here blocks Advance in this
          walkthrough.
        </p>
      </div>

      {readiness.layers.map((layer) => {
        const counts = layerCounts(layer)
        return (
          <div key={layer.key}>
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {layer.label}
              </h3>
              <div className="flex gap-1">
                {counts.fail > 0 && (
                  <Badge variant="destructive" className="px-1">
                    {counts.fail}
                  </Badge>
                )}
                {counts.warn > 0 && (
                  <Badge variant="warning" className="px-1">
                    {counts.warn}
                  </Badge>
                )}
                {counts.pass > 0 && (
                  <Badge variant="secondary" className="px-1">
                    {counts.pass}
                  </Badge>
                )}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{layer.description}</p>
            {layer.items.length === 0 ? (
              <p className="py-1 text-xs text-muted-foreground">Nothing to check.</p>
            ) : (
              <ul className="divide-y">
                {layer.items.map((item) => (
                  <Item key={item.key} item={item} onJumpToField={onJumpToField} />
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}
