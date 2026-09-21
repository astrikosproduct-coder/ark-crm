import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { api } from '@/lib/api'
import { stageNumberOf } from '@/lib/pipeline'

/** What backend/app/pursuit_erasure.py::plan answers. */
interface ErasePlan {
  root: string
  name: string
  records: { module: string; noun: string; id: string; name: string; stage: string | null }[]
  has_history: boolean
  groups: string[]
  registrations: string[]
  expansion_leads: string[]
}

const COLLECTIONS = ['leads', 'opportunities', 'deals', 'registrations', 'pursuit_groups']

/**
 * The "delete this whole pursuit" half of a delete dialog — open to every role
 * (decided 21 Sep 2026; app/routers/pursuit_erase.py).
 *
 * A checkbox first, as asked for: ticking it says the whole chain goes — the
 * Lead, the Opportunity, the Deal and all their history. Then the pursuit's
 * name is typed, because nothing brings it back. Accounts, Contacts, partner
 * registrations and other pursuits stay, only unlinked.
 */
export function useErasePursuit(recordId: string, enabled: boolean, onErased: () => void) {
  const queryClient = useQueryClient()
  const plan = useQuery({
    queryKey: ['pursuit-erase', recordId],
    queryFn: async () => (await api.get<ErasePlan>(`/pursuits/${recordId}/erase`)).data,
    enabled: enabled && Boolean(recordId),
    staleTime: 0,
  })
  const erase = useMutation({
    mutationFn: async (confirm: string) => {
      await api.post(`/pursuits/${recordId}/erase`, { confirm })
    },
    onSuccess: () => {
      onErased()
      for (const record of plan.data?.records ?? []) {
        queryClient.removeQueries({ queryKey: ['record', record.module, record.id] })
      }
      queryClient.removeQueries({ queryKey: ['pursuit-erase', recordId] })
      for (const collection of COLLECTIONS) {
        void queryClient.invalidateQueries({ queryKey: ['list', collection] })
        void queryClient.invalidateQueries({ queryKey: ['collection', collection] })
      }
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  return { plan, erase }
}

export function EraseSection({
  plan,
  checked,
  onChecked,
  typed,
  onTyped,
}: {
  plan: ErasePlan | undefined
  checked: boolean
  onChecked: (checked: boolean) => void
  typed: string
  onTyped: (value: string) => void
}) {
  return (
    <div className="space-y-2 rounded-md border border-destructive/40 p-3 text-sm">
      <label className="flex items-start gap-2">
        <Checkbox className="mt-0.5" checked={checked} onCheckedChange={(c) => onChecked(c === true)} />
        <span>
          <span className="font-medium">Also delete everything linked to this pursuit.</span>{' '}
          The Lead, Opportunity, Deal and all their history are deleted for good. This can&apos;t be undone.
        </span>
      </label>
      {checked && plan && (
        <>
          <Bullets
            items={[
              ...plan.records.map(
                (r) => `${r.noun}: ${r.name}${r.stage ? ` · Stage ${stageNumberOf(r.stage) ?? r.stage}` : ''}`
              ),
            ]}
          />
          <Bullets
            className="text-muted-foreground"
            items={[
              'Accounts and Contacts stay — other pursuits use them.',
              plan.registrations.length > 0 && 'Partner registrations stay, unlinked from it.',
              plan.groups.length > 0 && 'It leaves its pursuit group. A group left with one pursuit is closed.',
              plan.expansion_leads.length > 0 && 'Expansion leads opened off its Deal stay, unlinked.',
              'One line in the history keeps who deleted it, and when.',
            ]}
          />
          <label className="block space-y-1">
            <span>
              Type <span className="font-medium">{plan.name}</span> to confirm
            </span>
            <Input value={typed} onChange={(e) => onTyped(e.target.value)} autoComplete="off" />
          </label>
        </>
      )}
    </div>
  )
}

export function nameMatches(plan: ErasePlan | undefined, typed: string): boolean {
  return Boolean(plan) && typed.trim().toLowerCase() === plan!.name.trim().toLowerCase()
}

/**
 * The whole dialog, for an Opportunity or a Deal — neither had a delete of its
 * own on screen, and deleting one alone would leave its Lead converted into
 * nothing. The checkbox is still there, and must be ticked, so the statement
 * the user agrees to is the same one on every record.
 */
export function ErasePursuitDialog({
  open,
  recordId,
  noun,
  onClose,
  onErased,
}: {
  open: boolean
  recordId: string
  noun: string
  onClose: () => void
  onErased: () => void
}) {
  const [checked, setChecked] = useState(false)
  const [typed, setTyped] = useState('')
  const { plan, erase } = useErasePursuit(recordId, open, onErased)

  useEffect(() => {
    if (open) {
      setChecked(false)
      setTyped('')
    }
  }, [open])

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !erase.isPending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Delete this {noun} for good?</DialogTitle>
          <DialogDescription>{plan.data?.name ?? recordId}</DialogDescription>
        </DialogHeader>

        {plan.isLoading ? (
          <p className="text-muted-foreground text-sm">Checking what is linked to it…</p>
        ) : plan.isError ? (
          <ErrorNotice error={plan.error} />
        ) : (
          <div className="space-y-3 text-sm">
            <p>A {noun} is one step of a pursuit, so it is deleted with the rest of it.</p>
            <EraseSection plan={plan.data} checked={checked} onChecked={setChecked} typed={typed} onTyped={setTyped} />
          </div>
        )}

        {erase.isError && <ErrorNotice error={erase.error} />}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={erase.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={!checked || !nameMatches(plan.data, typed) || erase.isPending}
            onClick={() => erase.mutate(typed)}
          >
            {erase.isPending ? 'Deleting…' : 'Delete the whole pursuit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Delete, on an Opportunity or a Deal page — for every role. */
export function ErasePursuitButton({
  recordId,
  noun,
  disabled,
  onErased,
}: {
  recordId: string
  noun: string
  disabled?: boolean
  onErased: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} disabled={disabled}>
        <Trash2Icon className="size-4" />
        Delete
      </Button>
      <ErasePursuitDialog open={open} recordId={recordId} noun={noun} onClose={() => setOpen(false)} onErased={onErased} />
    </>
  )
}
