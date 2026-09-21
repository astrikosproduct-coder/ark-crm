import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ErrorNotice } from '@/components/ui/notice'
import { useDeleteRegistration, useRegistrationDependents } from '@/lib/registrations'

interface Props {
  open: boolean
  registrationId: string
  registrationName: string
  /** Offer "Withdraw instead" when the registration is still live. */
  canWithdraw: boolean
  onWithdrawInstead: () => void
  onClose: () => void
  onDeleted: () => void
}

/**
 * Delete a deal registration — only while nothing depends on it.
 *
 * Once a lead exists the registration is part of that pursuit's history, and
 * once a conflict names it, part of an adjudication. Neither is deleted from
 * here (the server refuses too, and the database refuses a lead's link). The
 * way to end a live registration is Withdraw, which asks what happens to the
 * pursuit instead of deleting it.
 */
export function DeleteRegistrationDialog({
  open,
  registrationId,
  registrationName,
  canWithdraw,
  onWithdrawInstead,
  onClose,
  onDeleted,
}: Props) {
  const { data: dependents, isLoading } = useRegistrationDependents(registrationId, open)
  const remove = useDeleteRegistration(registrationId, onDeleted)

  const blocked = Boolean(dependents && (dependents.leads.length > 0 || dependents.conflicts.length > 0))

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !remove.isPending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{blocked ? "This registration can't be deleted" : 'Delete registration'}</DialogTitle>
          <DialogDescription>{registrationName}</DialogDescription>
        </DialogHeader>

        {isLoading || !dependents ? (
          <p className="text-muted-foreground text-sm">Checking what depends on it…</p>
        ) : blocked ? (
          <div className="space-y-3 text-sm">
            <p>Other records depend on it:</p>
            {dependents.leads.length > 0 && (
              <div>
                <p className="text-muted-foreground mb-1">Leads created from it</p>
                <ul className="list-disc space-y-0.5 pl-5">
                  {dependents.leads.map((lead) => (
                    <li key={lead.id}>
                      <Link className="underline underline-offset-2" to={`/leads/${lead.id}`} onClick={onClose}>
                        {lead.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {dependents.conflicts.length > 0 && (
              <div>
                <p className="text-muted-foreground mb-1">Conflicts that name it</p>
                <ul className="list-disc space-y-0.5 pl-5">
                  {dependents.conflicts.map((conflict) => (
                    <li key={conflict.id}>{conflict.name}</li>
                  ))}
                </ul>
              </div>
            )}
            {canWithdraw && (
              <p className="text-muted-foreground">
                Partner pulled out? Withdraw it instead. You&apos;ll choose what happens to the pursuit.
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm">
            No lead or conflict depends on it. Deleting removes it for good.
          </p>
        )}

        {remove.isError && <ErrorNotice error={remove.error} />}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={remove.isPending}>
            {blocked ? 'Close' : 'Cancel'}
          </Button>
          {blocked && canWithdraw && (
            <Button type="button" onClick={onWithdrawInstead}>
              Withdraw instead
            </Button>
          )}
          {!blocked && dependents && (
            <Button
              type="button"
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {remove.isPending ? 'Deleting…' : 'Delete registration'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
