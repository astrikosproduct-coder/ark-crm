import type { ReactNode } from 'react'
import { useQueries, useQueryClient, useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangleIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { api } from '@/lib/api'
import { collectionFor, displayNameOf, fieldOf, fieldsOf, idOf } from '@/lib/spec'

/**
 * Retire a record: deactivate it, or delete it outright when nothing depends
 * on it.
 *
 * WHY THIS LISTS RECORDS INSTEAD OF COUNTING THEM
 * -----------------------------------------------
 * The first version asked the list endpoint `?end_client=ACC-019&_limit=1` for
 * each referring field and summed X-Total-Count. That is fragile in a way that
 * produced phantom references: a filter is a string comparison, so an empty or
 * unexpected id can match every row whose field is simply blank — the mock
 * matcher compares `String(value ?? '')`, and '' equals ''. A reviewer was
 * shown "7 records still reference this account" for an account created
 * seconds earlier.
 *
 * So nothing is counted or inferred any more. The rows are fetched and the
 * value is compared here, field by field, and only a row whose field ACTUALLY
 * HOLDS this id is a reference. Having the row in hand means the dialog can
 * name it — "LEAD-00118 · Cognus Platform — End Client" — which is both what
 * the reviewer asked for and impossible to fake: if a reference is listed, it
 * can be clicked and checked.
 */

type Row = Record<string, unknown>

export interface ReferrerSpec {
  /** The collection to scan, as the list endpoint names it. */
  collection: string
  /** The module whose register fields are read. Differs for registrations. */
  module: string
  /** Route prefix for the link, e.g. '/leads'. Omitted = not linkable. */
  basePath?: string
}

export interface DeleteRecordDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The collection the record itself lives in — 'accounts', 'contacts'. */
  collection: string
  recordId: string
  recordName: string
  /** Singular noun for the copy: 'account', 'contact'. */
  noun: string
  /** True when the record is currently active. */
  active: boolean
  /** lookup_target of this record type, as the register spells it. */
  lookupTarget: string
  referrers: ReferrerSpec[]
  onDeleted: () => void
  onDeactivated?: () => void
  /**
   * Shown in place of the default "nothing uses this" line when the record is
   * free to delete. Lets a screen explain the choice in its own words instead
   * of the generic sentence.
   */
  guidance?: ReactNode
}

interface Reference {
  collection: string
  basePath?: string
  id: string
  label: string
  /** The label of the field that points here, e.g. 'End Client'. */
  via: string
}

export function DeleteRecordDialog({
  open,
  onOpenChange,
  collection,
  recordId,
  recordName,
  noun,
  active,
  lookupTarget,
  referrers,
  onDeleted,
  onDeactivated,
  guidance,
}: DeleteRecordDialogProps) {
  const queryClient = useQueryClient()

  /** api_names on `module` whose lookup target is this record type. */
  const pointingFields = (module: string) =>
    fieldsOf(module)
      .filter(
        (f) => f.type === 'lookup' && collectionFor(f.lookup_target) === collectionFor(lookupTarget)
      )
      .map((f) => f.api_name)

  const scans = useQueries({
    queries: referrers.map((ref) => ({
      queryKey: ['refs', collection, recordId, ref.collection],
      // A blank id must never be scanned — that is the exact condition that
      // made the old counting version hallucinate.
      enabled: open && Boolean(recordId),
      staleTime: 0,
      queryFn: async (): Promise<Reference[]> => {
        const fields = pointingFields(ref.module)
        if (fields.length === 0) return []

        const rows = (await api.get<Row[]>(`/${ref.collection}`)).data
        if (!Array.isArray(rows)) return []

        const hits: Reference[] = []
        for (const row of rows) {
          for (const field of fields) {
            const value = row[field]
            // The ONLY thing that counts as a reference: the field actually
            // holds this id. Not "the field could point at one".
            const matches = Array.isArray(value)
              ? value.some((v) => v === recordId)
              : value === recordId
            if (!matches) continue

            hits.push({
              collection: ref.collection,
              basePath: ref.basePath,
              id: idOf(row) || String(row.id ?? ''),
              label: displayNameOf(row) || idOf(row),
              via: fieldOf(ref.module, field)?.label ?? field,
            })
          }
        }
        return hits
      },
    })),
  })

  const scanning = scans.some((q) => q.isLoading)
  const failed = scans.some((q) => q.isError)
  const references = scans.flatMap((q) => q.data ?? [])
  const blocked = references.length > 0

  const invalidate = () => {
    for (const key of [
      ['collection', collection],
      ['list', collection],
      ...referrers.map((r) => ['list', r.collection]),
      ...referrers.map((r) => ['collection', r.collection]),
    ]) {
      void queryClient.invalidateQueries({ queryKey: key })
    }
  }

  const deactivate = useMutation({
    mutationFn: async () => {
      await api.patch(`/${collection}/${recordId}/active`, { active: !active })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['record', collection, recordId] })
      invalidate()
      onOpenChange(false)
      onDeactivated?.()
    },
  })

  const remove = useMutation({
    mutationFn: async () => {
      await api.delete(`/${collection}/${recordId}`)
    },
    onSuccess: () => {
      // Order matters: leave the screen before the record query can refetch a
      // 404 and unmount this dialog mid-callback.
      onOpenChange(false)
      onDeleted()
      queryClient.removeQueries({ queryKey: ['record', collection, recordId] })
      queryClient.removeQueries({ queryKey: ['refs', collection, recordId] })
      invalidate()
    },
  })

  const busy = remove.isPending || deactivate.isPending
  const error = remove.error ?? deactivate.error

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Delete {recordName}?</DialogTitle>
          <DialogDescription>
            {!active
              ? `This ${noun} is already inactive.`
              : blocked
                ? `This ${noun} is used on ${references.length} ${references.length === 1 ? 'record' : 'records'}, so it can't be deleted.`
                : `This ${noun} isn't used anywhere.`}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-72 overflow-y-auto py-2 text-sm">
          {scanning ? (
            <p className="text-muted-foreground">Checking what uses this {noun}…</p>
          ) : failed ? (
            <p className="text-destructive">
              We couldn&apos;t check where this {noun} is used, so it can&apos;t be deleted right now. Try
              again in a moment.
            </p>
          ) : blocked ? (
            <div className="border-destructive/40 bg-destructive/5 space-y-2 rounded-md border p-3">
              <p className="text-destructive flex items-center gap-1.5 font-medium">
                <AlertTriangleIcon className="size-4 shrink-0" />
                Used on {references.length} {references.length === 1 ? 'record' : 'records'}
              </p>
              <ul className="space-y-1">
                {references.map((r) => (
                  <li key={`${r.collection}:${r.id}:${r.via}`} className="text-muted-foreground">
                    {r.basePath ? (
                      <Link
                        className="underline underline-offset-2"
                        to={`${r.basePath}/${r.id}`}
                        onClick={() => onOpenChange(false)}
                      >
                        {r.label || r.id}
                      </Link>
                    ) : (
                      <span>{r.label || r.id}</span>
                    )}
                    <span className="text-xs"> · {r.via}</span>
                  </li>
                ))}
              </ul>
              {active && (
                <Bullets
                  className="text-muted-foreground"
                  items={[
                    'Deactivate it instead.',
                    'It stops appearing in new picks.',
                    'The records above keep showing its name.',
                  ]}
                />
              )}
            </div>
          ) : (
            guidance ?? (
              <Bullets
                className="text-muted-foreground"
                items={['Delete removes it for good.', 'Deactivate hides it but keeps it.']}
              />
            )
          )}

          {error && <ErrorNotice className="mt-3" error={error} />}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          {/* Only offered while the record is still active. Reactivating is not
              a deletion concern and lives on the record header instead. */}
          {active && (
            <Button variant="outline" onClick={() => deactivate.mutate()} disabled={busy}>
              {deactivate.isPending ? 'Saving…' : 'Deactivate'}
            </Button>
          )}
          <Button
            variant="destructive"
            onClick={() => remove.mutate()}
            // Blocked while anything uses it, and while the check is still
            // running or has failed — never delete on an unknown.
            disabled={busy || scanning || failed || blocked}
            title={blocked ? `Used on ${references.length} ${references.length === 1 ? 'record' : 'records'}` : undefined}
          >
            {remove.isPending ? 'Deleting…' : 'Delete permanently'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
