import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'

/**
 * User feedback — backend/app/routers/feedback.py (UX roadmap item 2).
 *
 * Anyone with a role sends; only DEVELOPER reads and triages, and the SERVER
 * enforces that. `isDeveloper` below only decides what to draw — a non-developer
 * who reaches the inbox by URL gets the server's 403, shown as such.
 */

export const DEVELOPER_ROLE = 'DEVELOPER'

export interface FeedbackItem {
  id: string
  feedback_id: string
  category: string
  message: string
  page_path: string | null
  record_ref: string | null
  status: string
  created_by: string
  created_by_name: string | null
  created_at: string
  read_by: string | null
  read_at: string | null
}

export function useIsDeveloper(): boolean {
  const { user } = useAuth()
  return user?.roles.includes(DEVELOPER_ROLE) ?? false
}

export function useSendFeedback() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { category: string; message: string; page_path: string; record_ref: string | null }) =>
      (await api.post<FeedbackItem>('/feedback', body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['feedback'] }),
  })
}

export function useFeedbackList(enabled: boolean) {
  return useQuery({
    queryKey: ['feedback', 'list'],
    queryFn: async () => {
      const res = await api.get<FeedbackItem[]>('/feedback')
      return { items: res.data, newCount: Number(res.headers['x-new-count'] ?? 0) }
    },
    enabled,
    // The badge should notice new feedback without a reload, cheaply.
    refetchInterval: enabled ? 60_000 : false,
  })
}

export function useSetFeedbackStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      (await api.patch<FeedbackItem>(`/feedback/${id}`, { status })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['feedback'] }),
  })
}

/** The record a page is about, from its path — /leads/LEAD-00118 → LEAD-00118. */
export function recordRefOf(pathname: string): string | null {
  const last = pathname.split('/').filter(Boolean).pop() ?? ''
  return /^[A-Z]+-\d+/.test(last) ? last : null
}
