import * as React from 'react'

import { Input } from '@/components/ui/input'

/**
 * A number box you type in, and only type in.
 *
 * WHY THIS IS NOT `<input type="number">`
 * ---------------------------------------
 * The native number input ships a spinner — the two little arrows — and three
 * behaviours bolted to it that nobody asked for on a CRM form:
 *
 *   1. CLICKING an arrow steps the value. Fine in isolation; the arrows sit
 *      exactly where a user reaches to place the caret at the end of a figure,
 *      so a mis-click silently edits TCV by 1.
 *   2. SCROLLING over a focused field steps it. A long stage tab is scrolled
 *      constantly, and a wheel that passes over a focused Probability % turns
 *      70 into 64 with no click, no keystroke and nothing on screen to say it
 *      happened. This is the dangerous one.
 *   3. ARROW KEYS step it, so Up/Down cannot move the caret between rows the
 *      way they do in every other field on the form.
 *
 * Hiding the arrows with `appearance: none` removes the picture and leaves all
 * three behaviours, which is worse than leaving them visible — the value still
 * changes and the control no longer looks like something that would. So the
 * type goes instead.
 *
 * `inputMode="decimal"` keeps the numeric keypad on a phone, which is the one
 * thing type="number" was genuinely buying.
 *
 * A SECOND BUG THIS FIXES: a native number input reports value `''` for an
 * entry the browser considers invalid — "1.2.3", a lone "-", "1e" mid-typing —
 * so `Number(e.target.value)` saw an empty string and the field CLEARED itself
 * as the user typed. Here the raw text is kept while it is being typed and only
 * parsed when it is a number.
 *
 * WHAT IT EMITS: `number` for a complete number, `''` for an empty box. Never
 * NaN, and never a half-typed string — so every caller keeps the contract the
 * old `type="number"` handlers had, and validation upstream is unchanged.
 */

/** Characters a number may be built from, including partial entries. */
const NUMERIC = /^-?\d*\.?\d*$/

export interface NumericInputProps
  extends Omit<React.ComponentProps<'input'>, 'value' | 'onChange' | 'type'> {
  value: number | string | null | undefined
  onValueChange: (value: number | '') => void
}

export function NumericInput({ value, onValueChange, ...props }: NumericInputProps) {
  // What the user is typing, held only while it is not yet a number — "-",
  // "1." and "" all pass through here. Null means "show the value we were
  // given", which is what makes an externally-changed value (a computed field
  // recalculating, a stage switch reloading the record) still appear.
  const [typing, setTyping] = React.useState<string | null>(null)

  const shown = typing ?? (value ?? '')

  return (
    <Input
      {...props}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={String(shown)}
      onChange={(e) => {
        const next = e.target.value.trim()
        if (next !== '' && !NUMERIC.test(next)) return // a letter is not a keystroke

        // "-" and "1." are on the way to a number and are not one yet, so they
        // are held as text rather than parsed to NaN and saved.
        const parsed = next === '' ? '' : Number(next)
        if (next === '' || Number.isFinite(parsed)) {
          setTyping(next === String(parsed) ? null : next)
          onValueChange(parsed as number | '')
        } else {
          setTyping(next)
        }
      }}
      onBlur={(e) => {
        setTyping(null)
        props.onBlur?.(e)
      }}
    />
  )
}
