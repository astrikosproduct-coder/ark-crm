import { useState } from 'react'
import { AlertTriangleIcon, CheckCircle2Icon, HistoryIcon, UploadIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { dateTime as fmtDateTime } from '@/lib/format'
import { ErrorBox, LoadingRow, Mono, Row, Table } from './shared'
import { errorMessage } from '@/lib/admin'
import {
  useDraftStatus,
  useMetadataVersions,
  usePublishMetadata,
  useRollbackMetadata,
  type MetadataVersion,
} from '@/lib/metadata'

/**
 * Review, publish, and the version history.
 *
 * THE LIFECYCLE THIS SCREEN COMPLETES
 * ------------------------------------
 *   edit the draft -> review what changed -> publish -> immutable snapshot
 *   -> spec/*.json regenerated -> the frontend reads it
 *
 * Publishing is the only thing in the whole metadata layer that changes what a
 * user sees. Everything up to it is a draft nobody else is looking at, which is
 * what makes the review step real: a half-finished change can sit here for a
 * week without affecting a single screen.
 *
 * A draft that does not validate is refused by the API — no version is written
 * and no file is touched. The errors below are the same list the server checks
 * against, so what this screen shows is what publish will do.
 */
export function PublishTab() {
  const { data: draft, isLoading, isError, error } = useDraftStatus()
  const { data: versions = [] } = useMetadataVersions()
  const publish = usePublishMetadata()

  const [note, setNote] = useState('')
  const [result, setResult] = useState<string[] | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [rollbackTarget, setRollbackTarget] = useState<MetadataVersion | null>(null)

  if (isLoading) return <LoadingRow what="the draft" />
  if (isError) return <ErrorBox error={error} />
  if (!draft) return null

  const { validation } = draft

  const doPublish = async () => {
    setFailure(null)
    setResult(null)
    try {
      const published = await publish.mutateAsync(note)
      setResult(published.written)
      setNote('')
    } catch (err) {
      setFailure(errorMessage(err))
    }
  }

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------- current state */}
      <div className="rounded-md border p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h3 className="text-sm font-semibold">Draft</h3>
          {draft.published_version === null ? (
            <Badge variant="outline">Never published</Badge>
          ) : (
            <Badge variant="secondary">
              Published version {draft.published_version}
              {draft.published_at && ` · ${fmtDateTime(draft.published_at)}`}
            </Badge>
          )}
          {draft.has_changes ? (
            <Badge>{draft.changes.length || 'unpublished'} change
              {draft.changes.length === 1 ? '' : 's'} pending</Badge>
          ) : (
            <Badge variant="outline">No changes since the last publish</Badge>
          )}
        </div>

        <div className="text-muted-foreground grid grid-cols-3 gap-2 text-xs sm:grid-cols-6">
          {Object.entries(draft.counts).map(([key, value]) => (
            <div key={key}>
              <div className="text-foreground text-base font-semibold">{value}</div>
              {key.replace(/_/g, ' ')}
            </div>
          ))}
        </div>
      </div>

      {/* -------------------------------------------------- validation */}
      <div className="rounded-md border p-4">
        <div className="mb-2 flex items-center gap-2">
          {validation.ok ? (
            <CheckCircle2Icon className="size-4 text-emerald-600" />
          ) : (
            <AlertTriangleIcon className="text-destructive size-4" />
          )}
          <h3 className="text-sm font-semibold">
            {validation.ok ? 'The draft is publishable' : 'The draft cannot be published'}
          </h3>
        </div>

        {validation.errors.length > 0 && (
          <div className="mb-3">
            <p className="text-destructive mb-1 text-xs font-medium">
              {validation.errors.length} error(s) — publish is refused until these are fixed
            </p>
            <ul className="text-destructive list-disc space-y-0.5 pl-5 text-xs">
              {validation.errors.slice(0, 20).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        )}

        {validation.warnings.length > 0 && (
          <details className="mb-2">
            <summary className="text-muted-foreground cursor-pointer text-xs">
              {validation.warnings.length} warning(s) — register gaps, not blockers
            </summary>
            <ul className="text-muted-foreground mt-1 list-disc space-y-0.5 pl-5 text-xs">
              {validation.warnings.slice(0, 40).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </details>
        )}

        {validation.orphaned_sidecar_refs.length > 0 && (
          <details>
            <summary className="cursor-pointer text-xs text-amber-600">
              {validation.orphaned_sidecar_refs.length} spec/extensions.json key(s) name a
              field this draft no longer carries
            </summary>
            <p className="text-muted-foreground mt-1 text-xs">
              extensions.json is hand-maintained and is not regenerated, so these entries have
              to be removed from that file by hand.
            </p>
            <ul className="text-muted-foreground mt-1 list-disc space-y-0.5 pl-5 text-xs">
              {validation.orphaned_sidecar_refs.map((ref) => (
                <li key={ref}>
                  <Mono>{ref}</Mono>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {/* ----------------------------------------------------- changes */}
      {draft.changes.length > 0 && (
        <div className="rounded-md border p-4">
          <h3 className="mb-2 text-sm font-semibold">
            What would be published ({draft.changes.length})
          </h3>
          <ul className="text-muted-foreground max-h-72 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs">
            {draft.changes.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ----------------------------------------------------- publish */}
      <div className="rounded-md border p-4">
        <h3 className="mb-1 text-sm font-semibold">Publish</h3>
        <p className="text-muted-foreground mb-3 text-xs">
          Freezes the draft as an immutable version and regenerates{' '}
          <code>spec/fields.json</code>, <code>spec/picklists.json</code> and{' '}
          <code>spec/stages.json</code>. Those files are what the CRM reads, so this is the
          moment the change reaches the application. A running dev server picks it up on its
          next reload.
        </p>
        <Textarea
          rows={2}
          className="mb-3"
          placeholder="What changed, and why. This becomes the version note."
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <Button disabled={!validation.ok || publish.isPending} onClick={doPublish}>
          <UploadIcon className="size-4" />
          {publish.isPending ? 'Publishing…' : 'Publish'}
        </Button>

        {result && (
          <div className="mt-3 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3">
            <p className="text-sm font-medium">Published — it's live now</p>
            {/* The app loads the published register when a page opens
                (lib/spec/source.ts), so everyone gets this on their next page
                load — this tab included, which still runs on the old one. */}
            <p className="text-muted-foreground mt-1 text-xs">
              Everyone gets it the next time they open or reload a page.{' '}
              <button type="button" className="text-primary underline" onClick={() => window.location.reload()}>
                Reload now
              </button>
            </p>
            <ul className="text-muted-foreground mt-1 space-y-0.5 text-xs">
              {result.map((path) => (
                <li key={path}>
                  <Mono>{path}</Mono>
                </li>
              ))}
            </ul>
          </div>
        )}
        {failure && <p className="text-destructive mt-3 text-sm">{failure}</p>}
      </div>

      {/* ---------------------------------------------------- versions */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <HistoryIcon className="size-4" />
          <h3 className="text-sm font-semibold">Version history</h3>
        </div>
        <p className="text-muted-foreground mb-3 max-w-3xl text-xs">
          Published versions are immutable. Rolling back does not rewind history — it
          republishes an old snapshot as a NEW version, so what was live and when stays true.
          Nothing is destroyed on the way: a field the old snapshot does not carry is
          logically deleted and can be restored again.
        </p>

        {versions.length === 0 ? (
          <p className="text-muted-foreground py-6 text-sm">
            Nothing published yet. The first publish becomes version 1.
          </p>
        ) : (
          <Table
            head={
              <>
                <th className="w-20">Version</th>
                <th>Note</th>
                <th className="w-24">Fields</th>
                <th className="w-44">Published</th>
                <th className="w-28" />
              </>
            }
          >
            {versions.map((version) => (
              <Row key={version.id}>
                <td>
                  <Mono>#{version.version_no}</Mono>
                  {version.restored_from !== null && (
                    <div>
                      <Badge variant="outline">from #{version.restored_from}</Badge>
                    </div>
                  )}
                </td>
                <td>{version.note ?? <span className="text-muted-foreground">—</span>}</td>
                <td>{version.field_count}</td>
                <td className="text-muted-foreground text-xs">
                  {version.published_at
                    ? fmtDateTime(version.published_at)
                    : '—'}
                  {version.published_by && <div>by {version.published_by}</div>}
                </td>
                <td className="text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setRollbackTarget(version)}
                  >
                    Roll back
                  </Button>
                </td>
              </Row>
            ))}
          </Table>
        )}
      </div>

      <RollbackDialog version={rollbackTarget} onClose={() => setRollbackTarget(null)} />
    </div>
  )
}

function RollbackDialog({
  version,
  onClose,
}: {
  version: MetadataVersion | null
  onClose: () => void
}) {
  const rollback = useRollbackMetadata()
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    if (!version) return
    setError(null)
    try {
      await rollback.mutateAsync({ versionNo: version.version_no })
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={Boolean(version)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Roll back to version {version?.version_no}?</DialogTitle>
          <DialogDescription>
            The whole configuration returns to that snapshot.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <ul className="text-muted-foreground list-disc space-y-0.5 pl-5">
            <li>
              A new version is published carrying version {version?.version_no}'s
              configuration. History is extended, not rewound.
            </li>
            <li>
              Fields added since then are <strong>logically deleted</strong> — their data
              survives and they can be restored.
            </li>
            <li>
              Fields deleted since then come back, with the configuration they had.
            </li>
            <li>The spec files are regenerated from that snapshot.</li>
          </ul>
          {error && <p className="text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={rollback.isPending} onClick={confirm}>
            {rollback.isPending ? 'Rolling back…' : 'Roll back and publish'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
