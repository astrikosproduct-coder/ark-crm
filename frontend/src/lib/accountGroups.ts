import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { labelForValue } from '@/lib/spec'

/**
 * Groups of companies and the duplicate check on Accounts (Release 1.1).
 *
 * Every rule is the server's (backend/app/account_groups.py,
 * account_matching.py): a group is one level deep under its head, picking any
 * company of a group files the account under the head, and a save that would
 * duplicate a company is refused with the question to ask. This file reads
 * the group, sends "Make head of group", and describes a company in one line.
 */

/** A company the duplicate check found — POSSIBLE_DUPLICATE_ACCOUNT / ACCOUNT_EXISTS. */
export interface AccountMatch {
  account_id: string
  account_name: string
  region: string | null
  country: string | null
  active: boolean
  account_type: string[]
  /** The head of its group, or null when it is in none. */
  group_head: string | null
  group_name: string | null
}

type Row = Record<string, unknown>

/** The Country's name, from the register's list. */
export function countryLabel(code: unknown): string {
  return typeof code === 'string' && code ? labelForValue('countries', code) : ''
}

/**
 * "MEA - United Arab Emirates" — the grey line under an account's name in a
 * picker, which tells two companies of one registered name apart (7 Oct 2026).
 */
export function companyLine(row: Row): string {
  const region = typeof row.region === 'string' && row.region ? labelForValue('region', row.region) : ''
  return [region, countryLabel(row.country)].filter(Boolean).join(' - ')
}

/** What a company brings in — backend/app/group_revenue.py. USD. */
export interface GroupFigures {
  pipeline_usd: number
  pipeline_count: number
  won_usd: number
  won_count: number
}

export interface AccountGroup {
  /** The head first, then the rest by name; [] when the account is in no group. */
  companies: (Row & { figures: GroupFigures })[]
  /** Each pursuit counted once, however many of the group's companies it names. */
  total: GroupFigures | null
}

/** The same line for a duplicate-check match, with its group. */
export function matchLine(m: AccountMatch): string {
  const parts: string[] = []
  parts.push(companyLine(m as unknown as Row) || 'No Country yet')
  if (m.group_name) parts.push(m.group_head === m.account_id ? 'head of its group' : `${m.group_name} group`)
  if (!m.active) parts.push('Inactive')
  return parts.join(' · ')
}

/** The companies of an account's group, the head first, with what each brings in. */
export function useAccountGroup(accountId: string | undefined) {
  return useQuery({
    queryKey: ['account-group', accountId],
    queryFn: async () => (await api.get<AccountGroup>(`/accounts/${accountId}/group`)).data,
    enabled: Boolean(accountId),
  })
}

/** "Make head of group": this company becomes the head; the rest point at it. */
export function useMakeHead(accountId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await api.post<Row>(`/accounts/${accountId}/make-head`)).data,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-group'] }),
        queryClient.invalidateQueries({ queryKey: ['record', 'accounts'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'accounts'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'accounts'] }),
      ]),
  })
}
