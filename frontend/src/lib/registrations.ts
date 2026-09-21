import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

/**
 * Deal registration actions that are more than a field save — raising a
 * conflict, withdrawing, deleting. Every rule is the server's
 * (backend/app/registration_matching.py, registration_withdrawal.py); this file
 * fetches what a dialog needs to ask the right question and sends the answer.
 */

export interface PossibleConflictMatch {
  registration_id: string
  name: string
  partner: string | null
  partner_name: string | null
  project_name: string | null
  end_client_name: string | null
  submitted_date: string | null
  registration_status: string | null
  exclusivity_expiry_date: string | null
  /** Same partner twice is a duplicate entry, not a conflict. */
  same_partner: boolean
}

/** The answer a save carries back after the possible-conflict dialog. */
export interface ConflictAnswer {
  raise_conflict_with: string[]
  not_conflict_with?: string[]
  not_conflict_reason?: string
}

export interface NamedRef {
  id: string
  name: string
}

export interface RegistrationDependents {
  leads: NamedRef[]
  conflicts: NamedRef[]
}

export interface WithdrawalMember {
  record_id: string
  name: string | null
  partner_name: string | null
  stage_number: number | null
}

export interface WithdrawalPreview {
  can_withdraw: boolean
  blocked_reason: string | null
  pursuit: {
    record_id: string
    module: string
    name: string | null
    stage_number: number | null
    status: string | null
    is_open: boolean
    is_primary: boolean
    group_name: string | null
    other_open: WithdrawalMember[]
  } | null
  primary_handover: { registration_id: string; name: string } | null
}

export type PursuitAction = 'keep' | 'hold' | 'close'

/** Registration statuses a registration can still be withdrawn from. */
export const LIVE_REGISTRATION_STATUSES = new Set(['', 'SUBMITTED', 'ACKNOWLEDGED', 'ACTIVE', 'EXTENDED'])

/**
 * Everything a registration action can move: the registration and its lists,
 * its conflicts, the pursuit it protected, that pursuit's group and History.
 */
export function invalidateRegistrationWorld(queryClient: QueryClient) {
  const keys: unknown[][] = [
    ['record', 'registrations'],
    ['collection', 'registrations'],
    ['list', 'registrations'],
    ['collection', 'conflicts'],
    ['possible-conflicts'],
    ['registration-withdrawal'],
    ['registration-dependents'],
    ['pursuit-group'],
    ['audit-log'],
    ...['leads', 'opportunities', 'deals'].flatMap((c) => [
      ['record', c],
      ['collection', c],
      ['list', c],
    ]),
  ]
  return Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
}

export function usePossibleConflicts(registrationId: string | undefined) {
  return useQuery({
    queryKey: ['possible-conflicts', registrationId],
    queryFn: async () =>
      (await api.get<PossibleConflictMatch[]>(`/registrations/${registrationId}/possible-conflicts`)).data,
    enabled: Boolean(registrationId),
  })
}

export function useConflictCheck(registrationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (answer: ConflictAnswer) =>
      (await api.post(`/registrations/${registrationId}/conflict-check`, answer)).data,
    onSuccess: () => invalidateRegistrationWorld(queryClient),
  })
}

export function useWithdrawalPreview(registrationId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['registration-withdrawal', registrationId],
    queryFn: async () => (await api.get<WithdrawalPreview>(`/registrations/${registrationId}/withdrawal`)).data,
    enabled,
  })
}

export function useWithdrawRegistration(registrationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { reason: string; pursuit_action: PursuitAction | null; new_primary: string | null }) =>
      (await api.post(`/registrations/${registrationId}/withdraw`, body)).data,
    onSuccess: () => invalidateRegistrationWorld(queryClient),
  })
}

export function useRegistrationDependents(registrationId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['registration-dependents', registrationId],
    queryFn: async () =>
      (await api.get<RegistrationDependents>(`/registrations/${registrationId}/dependents`)).data,
    enabled,
  })
}

/**
 * `onDeleted` runs BEFORE anything refetches. The screen that asked is showing
 * the record just deleted: refetching it first answered 404, the page dropped
 * the dialog that owned the mutation, and a callback handed to mutate() never
 * fired — the user was left on a dead record instead of back on the list.
 */
export function useDeleteRegistration(registrationId: string, onDeleted?: () => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.delete(`/registrations/${registrationId}`)
    },
    onSuccess: () => {
      onDeleted?.()
      for (const queryKey of [
        ['record', 'registrations', registrationId],
        ['possible-conflicts', registrationId],
        ['registration-withdrawal', registrationId],
        ['registration-dependents', registrationId],
      ]) {
        queryClient.removeQueries({ queryKey })
      }
      void invalidateRegistrationWorld(queryClient)
    },
  })
}
