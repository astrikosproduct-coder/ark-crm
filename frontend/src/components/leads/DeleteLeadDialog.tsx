import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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
import { api } from '@/lib/api'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { fieldOf } from '@/lib/spec'

/** What backend/app/lead_deletion.py::deletion_plan answers. */
interface LinkedRecord {
  id: string
  name: string | null
  /** The lead's own api_names that name this record. */
  via: string[]
  /** What else uses it, by kind — empty when nothing does. */
  used_by: Record<string, number>
  deletable: boolean
}

type BlockerKind = 'opportunity' | 'deal' | 'registration' | 'pursuit_group' | 'expansion_of' | 'lead'

interface DeletionPlan {
  lead: string
  name: string | null
  blockers: { kind: BlockerKind; id: string; name: string | null }[]
  accounts: LinkedRecord[]
  contacts: LinkedRecord[]
}

const BLOCKER: Record<BlockerKind, { noun: string; path?: (id: string) => string }> = {
  opportunity: { noun: 'Opportunity it became', path: (id) => `/opportunities/${id}` },
  deal: { noun: 'Deal it became', path: (id) => `/deals/${id}` },
  registration: { noun: 'Deal registration', path: (id) => `/partners/registrations/${id}` },
  pursuit_group: { noun: 'Pursuit group' },
  expansion_of: { noun: 'Expansion of the deal', path: (id) => `/deals/${id}` },
  lead: { noun: 'Lead naming it as parent pursuit', path: (id) => `/leads/${id}` },
}

const USED_BY: Record<string, [string, string]> = {
  leads: ['lead', 'leads'],
  deals: ['deal', 'deals'],
  registrations: ['deal registration', 'deal registrations'],
  pursuit_groups: ['pursuit group', 'pursuit groups'],
  contacts: ['contact that stays', 'contacts that stay'],
}

function usedByText(usedBy: Record<string, number>): string {
  return Object.entries(usedBy)
    .map(([kind, count]) => {
      const [one, many] = USED_BY[kind] ?? [kind, kind]
      return `${count} other ${count === 1 ? one : many}`
    })
    .join(', ')
}

interface Props {
  open: boolean
  leadId: string
  onClose: () => void
  /** Runs BEFORE anything refetches — see useDeleteRegistration for why. */
  onDeleted: () => void
}

/**
 * Delete a lead — only while it is linked to nothing but Accounts and Contacts.
 *
 * Those are kept by default. One checkbox asks to delete them too, and even
 * then only the ones nothing else uses go; every linked record is listed with
 * what will happen to it, before anyone confirms. The server decides all of it
 * again on the delete itself (backend/app/lead_deletion.py).
 */
export function DeleteLeadDialog({ open, leadId, onClose, onDeleted }: Props) {
  const queryClient = useQueryClient()
  const [withLinked, setWithLinked] = useState(false)

  useEffect(() => {
    if (open) setWithLinked(false)
  }, [open])

  const { data: plan, isLoading, isError, error } = useQuery({
    queryKey: ['lead-deletion', leadId],
    queryFn: async () => (await api.get<DeletionPlan>(`/leads/${leadId}/deletion`)).data,
    enabled: open && Boolean(leadId),
    staleTime: 0,
  })

  const remove = useMutation({
    mutationFn: async () => {
      await api.delete(`/leads/${leadId}`, { params: withLinked ? { with_linked: true } : undefined })
    },
    onSuccess: () => {
      onDeleted()
      queryClient.removeQueries({ queryKey: ['record', 'leads', leadId] })
      queryClient.removeQueries({ queryKey: ['lead-deletion', leadId] })
      for (const collection of ['leads', 'accounts', 'contacts']) {
        void queryClient.invalidateQueries({ queryKey: ['list', collection] })
        void queryClient.invalidateQueries({ queryKey: ['collection', collection] })
      }
    },
  })

  const blocked = Boolean(plan && plan.blockers.length > 0)
  const linked = plan ? [...plan.accounts, ...plan.contacts] : []
  const deletable = linked.filter((r) => r.deletable)

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !remove.isPending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{blocked ? "This lead can't be deleted" : 'Delete this lead?'}</DialogTitle>
          <DialogDescription>{plan?.name ?? leadId}</DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <p className="text-muted-foreground text-sm">Checking what is linked to it…</p>
        ) : isError || !plan ? (
          <ErrorNotice error={error} />
        ) : blocked ? (
          <div className="space-y-2 text-sm">
            <p>It has already moved on in the pipeline:</p>
            <ul className="list-disc space-y-0.5 pl-5">
              {plan.blockers.map((b) => {
                const { noun, path } = BLOCKER[b.kind]
                const label = b.name ?? b.id
                return (
                  <li key={`${b.kind}:${b.id}`}>
                    <span className="text-muted-foreground">{noun}: </span>
                    {path ? (
                      <Link className="underline underline-offset-2" to={path(b.id)} onClick={onClose}>
                        {label}
                      </Link>
                    ) : (
                      label
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : (
          <div className="space-y-3 text-sm">
            <Bullets
              items={[
                "It's deleted for good, with its demo attendees and feature gaps.",
                'History keeps a note that it existed.',
              ]}
            />

            {linked.length > 0 && (
              <>
                {deletable.length > 0 ? (
                  <label className="flex items-start gap-2">
                    <Checkbox
                      className="mt-0.5"
                      checked={withLinked}
                      onCheckedChange={(checked) => setWithLinked(checked === true)}
                    />
                    <span>Also delete the accounts and contacts linked to this lead that nothing else uses</span>
                  </label>
                ) : (
                  <p className="text-muted-foreground">
                    Every account and contact linked to this lead is used elsewhere, so they are kept.
                  </p>
                )}
                <LinkedList title="Accounts" records={plan.accounts} withLinked={withLinked} />
                <LinkedList title="Contacts" records={plan.contacts} withLinked={withLinked} />
              </>
            )}
          </div>
        )}

        {remove.isError && <ErrorNotice error={remove.error} />}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={remove.isPending}>
            {blocked ? 'Close' : 'Cancel'}
          </Button>
          {plan && !blocked && (
            <Button type="button" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
              {remove.isPending
                ? 'Deleting…'
                : withLinked && deletable.length > 0
                  ? `Delete lead and ${deletable.length} linked record${deletable.length === 1 ? '' : 's'}`
                  : 'Delete lead'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function LinkedList({ title, records, withLinked }: { title: string; records: LinkedRecord[]; withLinked: boolean }) {
  if (records.length === 0) return null
  return (
    <div>
      <p className="text-muted-foreground mb-1 text-xs font-semibold tracking-wide uppercase">{title}</p>
      <ul className="divide-y rounded-md border">
        {records.map((r) => (
          <li key={r.id} className="flex items-start justify-between gap-3 px-3 py-1.5">
            <span className="min-w-0">
              <span className="font-medium">{r.name ?? r.id}</span>
              <span className="text-muted-foreground block text-xs">
                {r.via.map((api) => fieldOf('leads', api)?.label ?? api).join(' · ')}
              </span>
            </span>
            <span className={r.deletable && withLinked ? 'text-destructive shrink-0 text-xs' : 'text-muted-foreground shrink-0 text-right text-xs'}>
              {!r.deletable ? `Kept — used by ${usedByText(r.used_by)}` : withLinked ? 'Deleted' : 'Kept'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
