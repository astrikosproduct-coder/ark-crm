import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorBox, LoadingRow, Mono, Row, StatusBadge, Table } from './shared'
import { useMetadataStages, useUpdateStage, type MetadataStage } from '@/lib/metadata'

/**
 * The ten pipeline stages.
 *
 * The stage NUMBER is not editable. It is the identity every record stores, and
 * it is what the criterion codes (E4.1, X3.2) and module_split.json's ranges are
 * built from — renumbering a stage would repoint every one of them at once.
 * Everything else about a stage is editable, and sort_order moves it for display
 * without touching the number.
 *
 * A NOTE ON "Applies to"
 * ----------------------
 * The register says stages 4-7 apply to `lead`. That is known to be wrong —
 * spec/module_split.json's own note records it as a register correction, and
 * nothing in the application reads the column any more; the pipeline split
 * derives stage ownership from module_split.json's ranges instead. It is shown
 * here as the register has it rather than quietly corrected, because closing a
 * gap the Spec Health page is still reporting would hide it rather than fix it.
 */
export function StagesTab() {
  const { data: stages = [], isLoading, isError, error } = useMetadataStages()

  if (isLoading) return <LoadingRow what="stages" />
  if (isError) return <ErrorBox error={error} />

  return (
    <>
      <p className="text-muted-foreground mb-3 max-w-3xl text-sm">
        Ten stages, 0 to 9. The number is the identity records store and cannot be changed;
        name, probability band, owner role and phase can. "Applies to" is shown as the
        register has it — see the note in this screen's source about why stages 4-7 still say
        lead.
      </p>

      <Table
        head={
          <>
            <th className="w-16">Stage</th>
            <th>Name</th>
            <th className="w-32">Probability</th>
            <th className="w-40">Owner role</th>
            <th className="w-32">Bid phase</th>
            <th className="w-28">Applies to</th>
            <th className="w-24">Status</th>
            <th className="w-32" />
          </>
        }
      >
        {stages.map((stage) => (
          <StageRow key={stage.stage} stage={stage} />
        ))}
      </Table>
    </>
  )
}

function StageRow({ stage }: { stage: MetadataStage }) {
  const updateStage = useUpdateStage()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(stage.name)
  const [min, setMin] = useState(stage.prob_min?.toString() ?? '')
  const [max, setMax] = useState(stage.prob_max?.toString() ?? '')

  const save = () => {
    updateStage.mutate({
      stage: stage.stage,
      patch: {
        name: name.trim(),
        prob_min: min.trim() === '' ? null : Number(min),
        prob_max: max.trim() === '' ? null : Number(max),
      },
    })
    setEditing(false)
  }

  return (
    <Row muted={!stage.active}>
      <td>
        <Mono>{stage.stage}</Mono>
      </td>
      <td className="font-medium">
        {editing ? (
          <Input className="h-8" value={name} autoFocus onChange={(e) => setName(e.target.value)} />
        ) : (
          stage.name
        )}
      </td>
      <td>
        {editing ? (
          <div className="flex items-center gap-1">
            <Input className="h-8 w-14" value={min} onChange={(e) => setMin(e.target.value)} />
            <span className="text-muted-foreground">–</span>
            <Input className="h-8 w-14" value={max} onChange={(e) => setMax(e.target.value)} />
          </div>
        ) : stage.prob_min === null && stage.prob_max === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          `${stage.prob_min}–${stage.prob_max}%`
        )}
      </td>
      <td>
        <Mono>{stage.owner_role ?? '—'}</Mono>
      </td>
      <td>{stage.bid_phase ?? <span className="text-muted-foreground">—</span>}</td>
      <td>
        <Mono>{stage.applies_to ?? '—'}</Mono>
      </td>
      <td>
        <StatusBadge active={stage.active} />
      </td>
      <td className="text-right">
        {editing ? (
          <>
            <Button size="sm" onClick={save}>
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                updateStage.mutate({ stage: stage.stage, patch: { active: !stage.active } })
              }
            >
              {stage.active ? 'Deactivate' : 'Activate'}
            </Button>
          </>
        )}
      </td>
    </Row>
  )
}
