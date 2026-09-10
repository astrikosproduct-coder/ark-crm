import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

/**
 * Activate or deactivate a record.
 *
 * Lives here rather than inside the delete dialog because reactivating is not a
 * deletion concern: a retired record shows a Reactivate button in its own
 * header, next to Edit, where someone looking at an Inactive badge will
 * actually look for it. Burying it inside a dialog called "Delete" made the one
 * safe, reversible action the hardest thing on the screen to find.
 */
export function useSetRecordActive(
  collection: string,
  recordId: string,
  options?: { noun?: string; recordName?: string; onSuccess?: () => void }
) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (active: boolean) => {
      await api.patch(`/${collection}/${recordId}/active`, { active })
      return active
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['record', collection, recordId] })
      void queryClient.invalidateQueries({ queryKey: ['collection', collection] })
      void queryClient.invalidateQueries({ queryKey: ['list', collection] })
      options?.onSuccess?.()
    },
  })
}
