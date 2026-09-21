import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { fieldOf, labelForValue } from '@/lib/spec'
import type { Revenue } from '@/lib/revenue'

/**
 * Pursuit Groups — one project at one End Client pursued through more than one
 * partner, of which exactly one pursuit counts toward pipeline (Playbook §7.2).
 *
 * Every rule is the server's (backend/app/pursuits.py). This file fetches a
 * group, sends the three things a person does to one, and reads the server's
 * refusal codes so a screen can offer the next step instead of "could not be
 * saved". Nothing here decides what is primary.
 */

export interface PursuitMember {
  pursuit: string
  is_primary: boolean
  is_open: boolean
  module: 'leads' | 'opportunities' | 'deals'
  record_id: string
  name: string | null
  partner: string | null
  partner_name: string | null
  stage: string | null
  stage_number: number | null
  status: string | null
  chain: { module: string; record_id: string }[]
  revenue: Revenue | null
}

export interface PursuitAlert {
  code: 'NO_PRIMARY' | 'SECONDARY_AHEAD' | 'PRIMARY_CLOSED' | 'WON_WITH_OPEN_SECONDARIES'
  level: 'warning' | 'info'
  message: string
  details?: string[]
  pursuit?: string
  open?: string[]
}

export interface PursuitGroup {
  id: string
  group_id: string
  /** "Al Waha … at Madinat Al Waha …" — what a person calls the group. */
  name: string | null
  end_client: string | null
  end_client_name: string | null
  primary_pursuit: string | null
  primary_registration: string | null
  source_conflict: string | null
  created_by: string | null
  created_date: string
  modified_by: string | null
  modified_date: string
  members: PursuitMember[]
  alerts: PursuitAlert[]
}

/** The refusals a save or a conversion can meet, by the server's own code. */
export type PursuitErrorCode =
  | 'POSSIBLE_DUPLICATE'
  | 'PRIMARY_HAS_OPEN_SECONDARIES'
  | 'SECONDARY_CANNOT_WIN'
  | 'REMOVE_FROM_GROUP_FIRST'
  | 'NEW_PRIMARY_REQUIRED'
  | 'END_CLIENT_MISMATCH'
  | 'ALREADY_GROUPED'
  | 'GROUP_STILL_HAS_PURSUITS'
  | 'PRIMARY_REGISTRATION_REQUIRED'
  | 'FINAL_VALUE_MISMATCH'
  // Deal registrations — backend/app/registration_matching.py and
  // registration_withdrawal.py. Every one carries a sentence in `message`.
  | 'POSSIBLE_CONFLICT'
  | 'NOT_A_POSSIBLE_CONFLICT'
  | 'SAME_PARTNER_NOT_A_CONFLICT'
  | 'CONFLICT_EXISTS'
  | 'DECISION_RATIONALE_REQUIRED'
  | 'REGISTRATION_NOT_LIVE'
  | 'REGISTRATION_WITHDRAWN'
  | 'USE_WITHDRAW_ACTION'
  | 'REGISTRATION_HAS_DEPENDENTS'
  | 'WITHDRAWAL_REASON_REQUIRED'
  | 'PURSUIT_ACTION_REQUIRED'
  | 'CANNOT_WITHDRAW'
  | 'NOT_AN_OPEN_PURSUIT'

export interface PursuitMatch {
  pursuit: string
  module: string
  record_id: string
  group_id: string | null
  is_primary: boolean
  name?: string | null
  partner_name?: string | null
  stage_number?: number | null
  group_name?: string | null
}

export interface PursuitError {
  code: PursuitErrorCode
  message: string
  /** Bullets under the message — the way forward. */
  details?: string[]
  group_id?: string
  group_name?: string | null
  primary_pursuit?: string | null
  primary_name?: string | null
  matches?: PursuitMatch[]
  /** POSSIBLE_DUPLICATE on a lead from a registration: the reason Partners
   * recorded for "a different project", offered to pre-fill the answer. */
  suggested_reason?: string | null
  open?: { pursuit: string; module: string; record_id: string }[]
  options?: string[]
}

/** The server's structured refusal, when an axios error carries one. */
export function pursuitErrorOf(error: unknown): PursuitError | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'code' in detail) {
    return detail as PursuitError
  }
  return null
}

/**
 * The refusals a save can recover from by answering a question — each opens a
 * dialog in PursuitSaveResolver, and the save runs again with the answer. Every
 * OTHER refusal is shown where the save was made, in its own words.
 */
const ANSWERABLE = new Set<string>(['POSSIBLE_DUPLICATE', 'POSSIBLE_CONFLICT', 'PRIMARY_HAS_OPEN_SECONDARIES'])

export function answerableRefusalOf(error: unknown): PursuitError | null {
  const refusal = pursuitErrorOf(error)
  return refusal && ANSWERABLE.has(refusal.code) ? refusal : null
}

export const MODULE_PATH: Record<string, string> = {
  leads: '/leads',
  opportunities: '/opportunities',
  deals: '/deals',
}

export function pathOfRecord(recordId: string): string {
  const prefix = recordId.split('-', 1)[0]
  const module = prefix === 'LEAD' ? 'leads' : prefix === 'OPP' ? 'opportunities' : 'deals'
  return `${MODULE_PATH[module]}/${recordId}`
}

export function usePursuitGroup(groupId: string | null | undefined) {
  return useQuery({
    queryKey: ['pursuit-group', groupId],
    queryFn: async () => (await api.get<PursuitGroup>(`/pursuit-groups/${groupId}`)).data,
    enabled: Boolean(groupId),
  })
}

/** After any group change every pipeline list and record may have moved. */
function useInvalidatePursuits() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all(
      ['leads', 'opportunities', 'deals'].flatMap((collection) => [
        queryClient.invalidateQueries({ queryKey: ['list', collection] }),
        queryClient.invalidateQueries({ queryKey: ['collection', collection] }),
        queryClient.invalidateQueries({ queryKey: ['record', collection] }),
      ]).concat([
        queryClient.invalidateQueries({ queryKey: ['pursuit-group'] }),
        queryClient.invalidateQueries({ queryKey: ['audit-log'] }),
      ])
    )
}

export function useChangePrimary(groupId: string) {
  const invalidate = useInvalidatePursuits()
  return useMutation({
    mutationFn: async ({ recordId, reason }: { recordId: string; reason: string }) =>
      (await api.post<PursuitGroup>(`/pursuit-groups/${groupId}/primary`, { record_id: recordId, reason })).data,
    onSuccess: invalidate,
  })
}

export function useRemoveFromGroup(groupId: string) {
  const invalidate = useInvalidatePursuits()
  return useMutation({
    mutationFn: async ({
      recordId,
      reason,
      newPrimary,
    }: {
      recordId: string
      reason: string
      newPrimary?: string
    }) =>
      (
        await api.post<PursuitGroup | { dissolved: true; group_id: string }>(
          `/pursuit-groups/${groupId}/members/${recordId}/remove`,
          { reason, new_primary: newPrimary ?? null }
        )
      ).data,
    onSuccess: invalidate,
  })
}

/** Five characters, matching the server: enough to keep out "x" and "ok". */
export const MIN_REASON = 5

/** A pursuit's status as the register labels it. No status is Open. */
export function pursuitStatusLabel(module: string, status: string | null | undefined): string {
  const picklist = fieldOf(module, 'lead_status')?.picklist ?? fieldOf('leads', 'lead_status')?.picklist
  return labelForValue(picklist, status || 'OPEN')
}
