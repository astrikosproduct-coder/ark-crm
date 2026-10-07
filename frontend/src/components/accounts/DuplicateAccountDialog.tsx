import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Bullets } from '@/components/ui/notice'
import { matchLine, type AccountMatch } from '@/lib/accountGroups'

interface Props {
  open: boolean
  /** ACCOUNT_EXISTS: the one company it is. POSSIBLE_DUPLICATE_ACCOUNT: the similar ones. */
  exact: boolean
  matches: AccountMatch[]
  pending: boolean
  /** "Same company" — leave this form and use the one already there. */
  onUseExisting: (accountId: string) => void
  useExistingLabel: string
  /** "Same group" — save with Parent Account set to that company. */
  onJoinGroup: (accountId: string) => void
  /** "Different company" — save it on its own. One click, no reason (7 Oct 2026). */
  onDecline: () => void
  onClose: () => void
}

/**
 * "Is this company already in Accounts?" Asked by the server when an account
 * is saved beside a similar name (backend/app/account_groups.py::guard_duplicate).
 *
 * Three answers. Same company: use the one already there, nothing is saved.
 * Same group in another country: saved with Parent Account set, filed under
 * that group's head. Different company: saved on its own, and never asked
 * again about these companies.
 * The same registered name in the same Country has only the first answer.
 */
export function DuplicateAccountDialog({
  open,
  exact,
  matches,
  pending,
  onUseExisting,
  useExistingLabel,
  onJoinGroup,
  onDecline,
  onClose,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && !pending && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{exact ? 'This company is already in Accounts' : 'Is this company already in Accounts?'}</DialogTitle>
          <DialogDescription>
            {exact
              ? 'It has the same registered name, in the same Country.'
              : 'A company with a similar name is already here.'}
          </DialogDescription>
        </DialogHeader>

        {!exact && (
          <Bullets
            className="text-muted-foreground text-sm"
            items={[
              'Same company: use the one already here.',
              'Same group in another country: add it to that group.',
              'Different company: save it on its own.',
            ]}
          />
        )}

        <ul className="divide-y rounded-md border text-sm">
            {matches.map((m) => (
              <li key={m.account_id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0">
                  <a
                    className="font-medium underline underline-offset-2"
                    href={`/accounts/${m.account_id}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {m.account_name}
                  </a>
                  <span className="text-muted-foreground block text-xs">{matchLine(m)}</span>
                </span>
                <span className="flex shrink-0 gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant={exact ? 'default' : 'outline'}
                    disabled={pending}
                    onClick={() => onUseExisting(m.account_id)}
                  >
                    {useExistingLabel}
                  </Button>
                  {!exact && (
                    <Button type="button" size="sm" disabled={pending} onClick={() => onJoinGroup(m.account_id)}>
                      Add to its group
                    </Button>
                  )}
                </span>
              </li>
            ))}
          </ul>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          {!exact && (
            <Button type="button" variant="outline" onClick={onDecline} disabled={pending}>
              {pending ? 'Saving…' : "It's a different company"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
