import { addDays, differenceInCalendarDays, format, parseISO, startOfDay } from 'date-fns'

import { labelForValue, partnerRegistration } from '@/lib/spec'
import { withComputed } from '@/lib/spec/formula'
import type { Values } from '@/lib/spec/conditions'

/**
 * Deal registration lifecycle — Partner Playbook §6.2.
 *
 * Every number here comes from spec/extensions.json partner_registration, not
 * from a literal in a component: the 89-day exclusivity window, the
 * acknowledgement SLA and the 15-day threshold below which a live registration
 * reads as expiring. The register carries none of the three as data, which is
 * recorded as an open question rather than settled here.
 */

const RULES = partnerRegistration

/**
 * 89, not 90 — the window includes the start day, so 13 Jan runs to 12 Apr.
 * The register's prose says 90 and is wrong by one; the journey document is
 * authoritative. Flagged on Spec Health and in the field's own tooltip.
 */
export const EXCLUSIVITY_DAYS = RULES.exclusivity_days

/**
 * §6.2 states 48 hours. Both dates the rule reads are typed `date`, so elapsed
 * time is only knowable to the whole day and the rule is applied — and always
 * stated — as 2 days. Nothing in this module returns or formats hours.
 */
export const ACK_SLA_DAYS = RULES.acknowledgement_sla_days

export const EXPIRING_WITHIN_DAYS = RULES.expiring_within_days

/** The register's own date shape. Everything stored goes through here. */
export function isoDate(d: Date): string {
  return format(d, 'yyyy-MM-dd')
}

export function today(): Date {
  return startOfDay(new Date())
}

function asDate(value: unknown): Date | null {
  if (typeof value !== 'string' || !value) return null
  const d = parseISO(value)
  return Number.isNaN(d.getTime()) ? null : startOfDay(d)
}

export type ExclusivityState =
  | 'unacknowledged'
  | 'active'
  | 'expiring'
  | 'expired'
  | 'superseded'
  | 'rejected'

export interface RegistrationState {
  state: ExclusivityState
  /** Short label for the chip. */
  label: string
  /** Negative once the window has closed. Null before acknowledgement. */
  daysRemaining: number | null
  expiry: string | null
  acknowledged: boolean
  /** Whether an exclusivity window is currently protecting this partner. */
  protected: boolean
  /** Deadline for acknowledgement — submitted_date + the SLA, or null. */
  ackDueBy: string | null
  /** True while unacknowledged and past that deadline. */
  ackOverdue: boolean
  /**
   * Whole days from submission to acknowledgement, or to today while it is
   * still outstanding. Null without a submitted date. Never hours: see
   * ACK_SLA_DAYS.
   */
  ackDays: number | null
  /** Whether ackDays came in at or under the rule. Null when not yet knowable. */
  ackWithinSla: boolean | null
  /**
   * Set when registration_status in the record contradicts what the dates say.
   * Neither is silently believed — see the open question on the field.
   */
  storedStatusDisagrees: string | null
}

const CHIP_LABEL: Record<ExclusivityState, string> = {
  unacknowledged: 'Awaiting acknowledgement',
  active: 'Active',
  expiring: 'Expiring',
  expired: 'Expired',
  superseded: 'Superseded',
  rejected: 'Rejected',
}

/**
 * What a registration actually is right now, derived from its dates rather than
 * read off registration_status.
 *
 * The two can disagree — seed REG-00042 is stored Active with an expiry of
 * 12 Apr 2026 — because nothing in the register expires a registration. The
 * derived state wins on screen and the disagreement is reported next to it, so
 * a reviewer sees the missing rule instead of a plausible-looking chip.
 */
export function registrationState(raw: Values | undefined, now = today()): RegistrationState {
  // Through the form engine's evaluator, not off the stored value, so the chip
  // in a list cell and the Exclusivity Expiry Date field on the detail form can
  // never say different things. They otherwise would: seed REG-00042 stores
  // 12 Apr 2026 where add_days(13 Jan, 90) is the 13th. The register's formula
  // wins and the stored value is reported on the Spec Health page.
  const record = raw ? withComputed('partners', raw) : undefined

  const status = String(record?.registration_status ?? '')
  const expiryDate = asDate(record?.exclusivity_expiry_date)
  const expiry = expiryDate ? isoDate(expiryDate) : null
  const acknowledged = Boolean(record?.acknowledged_date)
  const submitted = asDate(record?.submitted_date)

  const ackDue = submitted ? addDays(submitted, ACK_SLA_DAYS) : null
  const ackDueBy = ackDue ? isoDate(ackDue) : null

  const daysRemaining = expiryDate ? differenceInCalendarDays(expiryDate, now) : null

  // Whole days only. Once acknowledged this is how long it took; while it is
  // outstanding it is how long it has been waiting, which is what the overdue
  // banner needs to say.
  const ackAgainst = asDate(record?.acknowledged_date) ?? now
  const ackDays = submitted ? differenceInCalendarDays(ackAgainst, submitted) : null

  const base = {
    daysRemaining,
    expiry,
    acknowledged,
    ackDueBy,
    ackOverdue: !acknowledged && Boolean(ackDue) && now > (ackDue as Date),
    ackDays,
    ackWithinSla: ackDays === null ? null : ackDays <= ACK_SLA_DAYS,
  }

  const settle = (state: ExclusivityState, disagrees: string | null = null): RegistrationState => ({
    ...base,
    state,
    label: CHIP_LABEL[state],
    protected: state === 'active' || state === 'expiring',
    storedStatusDisagrees: disagrees,
  })

  // A person set these deliberately; no date overrules them.
  if (status === 'SUPERSEDED') return settle('superseded')
  if (status === 'REJECTED') return settle('rejected')

  if (!acknowledged || daysRemaining === null) return settle('unacknowledged')

  const stored = labelForValue('partners__registration_status', status)

  if (daysRemaining < 0) {
    return settle(
      'expired',
      status === 'ACTIVE' || status === 'EXTENDED'
        ? `the record still says ${stored}, but the window closed ${Math.abs(daysRemaining)} days ago`
        : null
    )
  }

  if (daysRemaining <= EXPIRING_WITHIN_DAYS) return settle('expiring')
  return settle('active')
}

function days(n: number): string {
  return `${n} ${n === 1 ? 'day' : 'days'}`
}

/**
 * The acknowledgement SLA in words, always in whole days.
 *
 * "acknowledged in 1 day, inside the 2-day rule". §6.2 writes the rule as 48
 * hours, but submitted_date and acknowledged_date are both `date`, so an hour
 * count would be a number this data cannot support. Saying "2-day rule" is the
 * honest form of the same rule, and it is the only form used anywhere on screen.
 */
export function ackSlaText(state: RegistrationState): string {
  const rule = `${ACK_SLA_DAYS}-day rule`

  if (state.ackDays === null) {
    return `No submitted date, so the ${rule} cannot be judged`
  }

  if (state.acknowledged) {
    const took = state.ackDays === 0 ? 'the same day' : `in ${days(state.ackDays)}`
    return `Acknowledged ${took}, ${state.ackWithinSla ? 'inside' : 'outside'} the ${rule}`
  }

  if (state.ackDays === 0) return `Submitted today. The ${rule} runs from today`
  return state.ackWithinSla
    ? `Waiting ${days(state.ackDays)}, inside the ${rule}`
    : `Waiting ${days(state.ackDays)}, past the ${rule}`
}

/** "12 days left", "closed 128 days ago", "—". */
export function daysRemainingText(state: RegistrationState): string {
  const n = state.daysRemaining
  if (n === null) return '—'
  if (n < 0) return `closed ${days(Math.abs(n))} ago`
  if (n === 0) return 'closes today'
  return `${days(n)} left`
}

/**
 * The patch that acknowledgement writes.
 *
 * Every one of these five is stamped by ARK, never typed: the register marks
 * acknowledgement_sla_met and exclusivity_expiry_date Computed, and the other
 * three follow from the click. The two computed ones are snapshotted through
 * the form engine's own evaluator rather than recalculated here, so the stored
 * value and the value the detail form derives can never drift apart.
 */
export function acknowledgementPatch(record: Values, at = today()): Values {
  const start = isoDate(at)
  const patch: Values = {
    ...record,
    acknowledged_date: start,
    exclusivity_start_date: start,
    registration_status: 'ACTIVE',
  }

  const computed = withComputed('partners', patch)
  return {
    acknowledged_date: start,
    exclusivity_start_date: start,
    registration_status: 'ACTIVE',
    exclusivity_expiry_date: computed.exclusivity_expiry_date ?? null,
    acknowledgement_sla_met: computed.acknowledgement_sla_met ?? null,
  }
}

/** The window acknowledging today would open, for the confirmation modal. */
export function proposedWindow(at = today()): { start: string; expiry: string } {
  return { start: isoDate(at), expiry: isoDate(addDays(at, EXCLUSIVITY_DAYS)) }
}

/** Case- and punctuation-insensitive, so "DC-7 Facility" meets "dc7 facility". */
function slug(v: unknown): string {
  return String(v ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
}

/**
 * Other registrations on the same client and project by a different partner —
 * §6.2's own definition of a conflict.
 *
 * Detection only. No conflict record is created: nothing in the register says
 * whether ARK raises one or a person does, which is on the Spec Health page.
 */
export function collidingRegistrations(record: Values, all: Values[]): Values[] {
  return all.filter(
    (other) =>
      other.id !== record.id &&
      other.partner !== record.partner &&
      slug(other.end_client) === slug(record.end_client) &&
      slug(other.project_name) === slug(record.project_name)
  )
}

/**
 * The adjudication recorded against one PAIR of registrations, if there is one.
 *
 * Matched in either direction: the register names the two sides registration_a
 * and registration_b, but nothing says which of a colliding pair is which, and
 * the same conflict is reachable from either registration's screen.
 */
export function adjudicationFor(
  aId: unknown,
  bId: unknown,
  conflicts: Values[]
): Values | undefined {
  return conflicts.find(
    (c) =>
      (c.registration_a === aId && c.registration_b === bId) ||
      (c.registration_a === bId && c.registration_b === aId)
  )
}

/**
 * Which registration a recorded decision awarded the deal to.
 *
 * The picklist is written in terms of the record's own A/B slots
 * (AWARDED_TO_REGISTRATION_A), so resolving it to an actual registration id is
 * the only way a reader can tell who won without holding the slot order in
 * their head. BOTH_DECLINED resolves to nobody, which is a real outcome and not
 * a missing answer.
 */
export function adjudicationWinner(conflict: Values | undefined): string | null {
  if (!conflict) return null
  const decision = String(conflict.decision ?? '')
  if (decision === 'AWARDED_TO_REGISTRATION_A') return String(conflict.registration_a ?? '') || null
  if (decision === 'AWARDED_TO_REGISTRATION_B') return String(conflict.registration_b ?? '') || null
  return null
}

/** The registration that did NOT prevail, for the supersede prompt. */
export function adjudicationLoser(conflict: Values | undefined): string | null {
  if (!conflict) return null
  const decision = String(conflict.decision ?? '')
  if (decision === 'AWARDED_TO_REGISTRATION_A') return String(conflict.registration_b ?? '') || null
  if (decision === 'AWARDED_TO_REGISTRATION_B') return String(conflict.registration_a ?? '') || null
  return null
}
