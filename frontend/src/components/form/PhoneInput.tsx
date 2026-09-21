import { useState } from 'react'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface Props {
  id: string
  /** The dial codes, from the field's picklist. A key IS the code: "+971". */
  options: { key: string; label: string }[]
  value: unknown
  onChange: (value: string) => void
  invalid?: boolean
}

/**
 * Split a stored "+971 50 123 4567" into its dial code and the rest.
 *
 * Only a known code followed by a space counts. Anything else — a number saved
 * before this control existed, or one typed with its own "+" — comes back whole
 * as the number, with no code, so it is never silently re-prefixed.
 */
function splitPhone(value: unknown, codes: string[]): { code?: string; number: string } {
  const text = typeof value === 'string' ? value.trim() : ''
  const code = [...codes]
    .sort((a, b) => b.length - a.length)
    .find((c) => text.startsWith(`${c} `))
  return code ? { code, number: text.slice(code.length).trim() } : { number: text }
}

/**
 * A phone number with a dial-code dropdown in front of it.
 *
 * Stored as ONE string in the field's own column, so no schema changes and a
 * list, a search or an export reads it as the whole number. The code on its own
 * is never stored: with no number there is nothing to save, and the dropdown's
 * choice is held locally until one is typed. The default is the picklist's
 * first value, so the order is set in Administration, not here.
 */
export function PhoneInput({ id, options, value, onChange, invalid }: Props) {
  const parsed = splitPhone(
    value,
    options.map((o) => o.key)
  )
  const [pickedCode, setPickedCode] = useState(() => parsed.code ?? options[0]?.key)
  // A saved value's own code wins over the local choice.
  const code = parsed.code ?? pickedCode

  const combine = (nextCode: string | undefined, nextNumber: string) => {
    const number = nextNumber.trim()
    if (!number) return ''
    // A number that already carries its own "+" is kept as typed.
    if (number.startsWith('+') || !nextCode) return number
    return `${nextCode} ${number}`
  }

  return (
    <div className="flex gap-2">
      <Select
        value={code}
        onValueChange={(next) => {
          setPickedCode(next)
          if (parsed.number) onChange(combine(next, parsed.number))
        }}
      >
        <SelectTrigger
          aria-label="Country code"
          aria-invalid={invalid}
          className="w-36 shrink-0"
        >
          <SelectValue placeholder="Code" />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.key} value={o.key}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        id={id}
        type="tel"
        inputMode="tel"
        aria-invalid={invalid}
        className="min-w-0 flex-1"
        value={parsed.number}
        onChange={(e) => onChange(combine(code, e.target.value))}
      />
    </div>
  )
}
