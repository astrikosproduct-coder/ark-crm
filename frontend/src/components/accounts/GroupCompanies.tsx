import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CrownIcon } from 'lucide-react'

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
import { companyLine, useAccountGroup, useMakeHead, type GroupFigures } from '@/lib/accountGroups'
import { money } from '@/lib/format'
import { displayNameOf, idOf, labelForValue } from '@/lib/spec'
import { cn } from '@/lib/utils'

/**
 * The companies of an account's group — the head first, then the rest by name
 * — with what each brings in and the group's total (Release 1.1).
 *
 * The figures are backend/app/group_revenue.py's: pursuits where the company is
 * the End Client or the Partner, by the dashboard's revenue rule, in USD. The
 * total counts each pursuit once. On a member, "Make head of group" turns it
 * into the head (backend/app/account_groups.py).
 */
export function GroupCompanies({ accountId }: { accountId: string }) {
  const { data, isLoading } = useAccountGroup(accountId)
  const [confirming, setConfirming] = useState(false)
  const makeHead = useMakeHead(accountId)

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>

  const rows = data?.companies ?? []
  if (rows.length === 0) {
    return (
      <p className="py-3 text-sm text-muted-foreground">
        This company isn't part of a group. To add it to one, edit it and pick a Parent Account.
      </p>
    )
  }

  const head = rows[0]
  const self = rows.find((r) => idOf(r) === accountId)
  const isHead = idOf(head) === accountId

  return (
    <div className="space-y-3 py-3">
      {!isHead && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            <CrownIcon className="size-4" />
            Make head of group
          </Button>
        </div>
      )}

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Account Name</th>
              <th className="px-3 py-2 font-medium">Region - Country</th>
              <th className="px-3 py-2 font-medium">Account Type</th>
              <th className="px-3 py-2 text-right font-medium">Open pursuits</th>
              <th className="px-3 py-2 text-right font-medium">Open pipeline (USD)</th>
              <th className="px-3 py-2 text-right font-medium">Deals won</th>
              <th className="px-3 py-2 text-right font-medium">Won (USD)</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => {
              const rid = idOf(r)
              const types = Array.isArray(r.account_type) ? (r.account_type as string[]) : []
              return (
                <tr key={rid} className={cn(rid === accountId && 'bg-muted/30')}>
                  <td className="px-3 py-2">
                    <Link className="font-medium underline-offset-2 hover:underline" to={`/accounts/${rid}`}>
                      {displayNameOf(r)}
                    </Link>
                    {rid === idOf(head) && <span className="text-muted-foreground ml-2 text-xs">Head</span>}
                    {r.active === false && <span className="text-muted-foreground ml-2 text-xs">Inactive</span>}
                  </td>
                  <td className="px-3 py-2">{companyLine(r)}</td>
                  <td className="px-3 py-2">
                    {types.map((t) => labelForValue('accounts__account_type', t)).join(', ')}
                  </td>
                  <Figures figures={r.figures} />
                </tr>
              )
            })}
          </tbody>
          {data?.total && (
            <tfoot className="border-t font-medium">
              <tr>
                <td className="px-3 py-2" colSpan={3}>
                  Group total
                </td>
                <Figures figures={data.total} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      <Bullets
        className="text-muted-foreground text-xs"
        items={[
          'Counts pursuits where the company is the End Client or the Partner.',
          'Open pipeline: open and on-hold Leads and Opportunities.',
          'Won: Deals whose PO has been received.',
          'The group total counts a pursuit once, even when it names two companies of the group.',
        ]}
      />

      <Dialog open={confirming} onOpenChange={(next) => !next && !makeHead.isPending && setConfirming(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Make {self ? displayNameOf(self) : 'this company'} the head of the group?</DialogTitle>
            <DialogDescription>
              {displayNameOf(head)} and the other companies will sit under it.
            </DialogDescription>
          </DialogHeader>
          <Bullets
            className="text-muted-foreground text-sm"
            items={['Every company stays in the group.', 'Nothing else on any record changes.']}
          />
          {makeHead.isError && <ErrorNotice error={makeHead.error} />}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={makeHead.isPending}>
              Cancel
            </Button>
            <Button
              onClick={() => makeHead.mutate(undefined, { onSuccess: () => setConfirming(false) })}
              disabled={makeHead.isPending}
            >
              {makeHead.isPending ? 'Saving…' : 'Make head of group'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** The four figure cells of a row: count, value, count, value. A dash for nothing. */
function Figures({ figures }: { figures: GroupFigures }) {
  return (
    <>
      <Cell value={figures.pipeline_count} />
      <Cell value={figures.pipeline_count ? money(figures.pipeline_usd) : 0} />
      <Cell value={figures.won_count} />
      <Cell value={figures.won_count ? money(figures.won_usd) : 0} />
    </>
  )
}

function Cell({ value }: { value: number | string }) {
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      {value ? value : <span className="text-muted-foreground">—</span>}
    </td>
  )
}
