import { CheckIcon } from 'lucide-react'
import { computeReadiness, type ProofField, type ReadinessItem } from '@/lib/readiness'
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
  /**
   * The Update Stage dialog's own ticks for the MANUAL checks. Given with
   * onToggleAttested, those checks render a real checkbox; without them they
   * stay drawn and unticked.
   */
  attested?: ReadonlySet<string>
  onToggleAttested?: (key: string) => void
}

/**
 * A checkbox that reads the record instead of accepting a click.
 *
 * Plain markup, not the Checkbox primitive — Radix's Checkbox IS a button, and
 * this sits inside the row's own button. Two nested buttons is invalid HTML,
 * so the tick is drawn instead of mounted.
 */
function ReadOnlyCheck({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-[4px] border',
        checked ? 'border-primary bg-primary text-primary-foreground' : 'border-input'
      )}
    >
      {checked && <CheckIcon className="size-3.5" />}
    </span>
  )
}

/**
 * Every field a criterion names, each with its own state — so a criterion over
 * two fields can never read as though one of them were the whole answer.
 */
function ProofList({ proofs, checked }: { proofs: ProofField[]; checked: boolean }) {
  return (
    <span className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
      <span>{checked ? 'From' : proofs.length > 1 ? `Needs all ${proofs.length}:` : 'Fill'}</span>
      {proofs.map(({ field, filled }) => (
        <span
          key={field.api_name}
          className={cn('inline-flex items-center gap-0.5', !filled && !checked && 'text-foreground')}
        >
          {filled && <CheckIcon className="size-3" aria-label="filled" />}
          {field.label}
        </span>
      ))}
    </span>
  )
}

/**
 * One criterion, as a checklist line.
 *
 * The box is DERIVED and therefore not operable: it reads the record, and the
 * way to tick it is to fill the fields it names. So the click does the useful
 * thing instead: it takes you to the first field still to fill — but only a
 * field the record can be edited on at the stage it is at.
 */
function Item({
  item,
  onJumpToField,
  attested,
  onToggleAttested,
}: {
  item: ReadinessItem
  onJumpToField?: (field: FieldSpec) => void
  attested?: ReadonlySet<string>
  onToggleAttested?: (key: string) => void
}) {
  // A check nothing on the record can settle here is ticked by the person, in
  // the dialog that moves the stage. Same box and row as every other check.
  if (item.manual) {
    const ticked = attested?.has(item.key) ?? false
    const text = (
      <span className="min-w-0 flex-1">
        <span className="text-sm">
          {item.code && <span className="text-muted-foreground">{item.code} · </span>}
          {item.label}
        </span>
        {item.askedAtStage !== undefined && item.proofs.length > 0 && (
          <span className="text-muted-foreground mt-0.5 block text-xs">
            Confirm now — {item.proofs.map((p) => p.field.label).join(' · ')}{' '}
            {item.proofs.length === 1 ? 'is' : 'are'} filled in once the record is at Stage {item.askedAtStage}.
          </span>
        )}
      </span>
    )
    if (!onToggleAttested) {
      return (
        <li className="flex items-start gap-2.5 py-1.5">
          <ReadOnlyCheck checked={false} />
          {text}
        </li>
      )
    }
    return (
      <li>
        <button
          type="button"
          role="checkbox"
          aria-checked={ticked}
          onClick={() => onToggleAttested(item.key)}
          className="hover:bg-accent/60 -mx-2 flex w-full items-start gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors"
        >
          <ReadOnlyCheck checked={ticked} />
          {text}
        </button>
      </li>
    )
  }

  const proof = item.proof
  const canJump = Boolean(proof && onJumpToField)

  // The record proves it, or the person has said so. A criterion the record
  // CANNOT prove may now be ticked by hand (16 Sep 2026) — the record is one
  // reading of a fact and the person moving the stage is another, and the tick
  // is recorded on the transition as their claim. A criterion the record does
  // prove stays derived: there is nothing for a person to add to it, and a box
  // that could be un-ticked would let the checklist contradict the record.
  const personTicked = attested?.has(item.key) ?? false
  const ticked = item.checked || personTicked
  const canTick = Boolean(onToggleAttested) && !item.checked

  const text = (
    <span className="min-w-0 flex-1">
      <span className={cn('text-sm', !ticked && 'text-foreground')}>
        {item.code && <span className="text-muted-foreground">{item.code} · </span>}
        {item.label}
      </span>
      {item.proofs.length > 0 && <ProofList proofs={item.proofs} checked={ticked} />}
    </span>
  )

  if (!canTick) {
    const body = (
      <>
        <ReadOnlyCheck checked={ticked} />
        {text}
      </>
    )
    if (!canJump) {
      return <li className="flex items-start gap-2.5 py-1.5">{body}</li>
    }
    return (
      <li>
        <button
          type="button"
          onClick={() => onJumpToField?.(proof as FieldSpec)}
          title={ticked ? undefined : `Go to ${proof?.label}`}
          className="hover:bg-accent/60 -mx-2 flex w-full items-start gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors"
        >
          {body}
        </button>
      </li>
    )
  }

  // Two targets on one row, because there are two useful answers: tick the box
  // to confirm it yourself, or click the criterion to go and fill the field
  // that would prove it. Separate buttons rather than one — a click meaning
  // either "I confirm this" or "take me there" depending on where it landed is
  // not a thing a checklist may be ambiguous about.
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <button
        type="button"
        role="checkbox"
        aria-checked={personTicked}
        aria-label={`Confirm: ${item.label}`}
        title="Tick to confirm this yourself — recorded on the stage move"
        onClick={() => onToggleAttested?.(item.key)}
        className="rounded-[4px]"
      >
        <ReadOnlyCheck checked={ticked} />
      </button>
      {canJump ? (
        <button
          type="button"
          onClick={() => onJumpToField?.(proof as FieldSpec)}
          title={`Go to ${proof?.label}`}
          className="hover:bg-accent/60 -mx-2 flex min-w-0 flex-1 items-start rounded-md px-2 text-left transition-colors"
        >
          {text}
        </button>
      ) : (
        text
      )}
    </li>
  )
}

/**
 * The criteria themselves, with no surrounding chrome. Shared by both Update
 * Stage dialogs, so a criterion reads and behaves identically wherever it is
 * met — including the click that drills down to the field behind it.
 */
export function ReadinessLayers({
  module,
  values,
  from,
  to,
  onJumpToField,
  className,
  attested,
  onToggleAttested,
}: Props) {
  const readiness = computeReadiness(module, values, from, to)

  return (
    <div className={cn('space-y-5', className)}>
      {readiness.layers.map((layer) => (
        <div key={layer.key}>
          <h3 className="text-muted-foreground mb-1 text-xs font-semibold tracking-wide uppercase">
            {layer.label}
          </h3>
          <ul className="divide-y">
            {layer.items.map((item) => (
              <Item
                key={item.key}
                item={item}
                onJumpToField={onJumpToField}
                attested={attested}
                onToggleAttested={onToggleAttested}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

/**
 * The criteria as a bordered card. Used inside the Update Stage dialog, where
 * they are the reason the dialog exists and belong on screen unprompted.
 *
 * The record page does not render this: it stood there as a permanent 360px
 * column beside every record, then as a Readiness drawer button in the header,
 * and both were removed on review — the dialog is where the question is asked.
 */
export function ReadinessPanel({ className, ...props }: Props) {
  return (
    <div className={cn('bg-card space-y-3 rounded-lg p-4 shadow-sm', className)}>
      <h2 className="text-sm font-semibold">
        Readiness — Stage {props.from} → Stage {props.to}
      </h2>
      <ReadinessLayers {...props} />
    </div>
  )
}
