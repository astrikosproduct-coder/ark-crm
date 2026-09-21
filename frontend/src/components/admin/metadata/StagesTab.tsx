import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorBox, LoadingRow, Mono, Row, StatusBadge, Table } from './shared'
import { useMetadataStages, useUpdateStage, type MetadataStage } from '@/lib/metadata'

/**
 * The ten pipeline stages — and THE ONE SOURCE of Progression % and
 * Probability %. Every Lead, Opportunity and Deal takes its stage's pair on
 * entering the stage (backend app/progression.py); a person who changes either
 * number on a record must give a justification.
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
        Ten stages, 0 to 9. Progression % and Probability % here are what every record takes when it
        enters the stage — Progression moves on our work, Probability on the client's decisions. Both
        are 0–100 in steps of 5; a change applies to records as they next enter the stage. The number
        is the identity records store and cannot be changed. "Applies to" is shown as the register
        has it — see the note in this screen's source about why stages 4-7 still say lead.
      </p>

      <Table
        head={
          <>
            <th className="w-16">Stage</th>
            <th>Name</th>
            <th className="w-28">Progression</th>
            <th className="w-28">Probability</th>
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
  const [progression, setProgression] = useState(stage.progression_pct?.toString() ?? '')
  const [probability, setProbability] = useState(stage.probability_pct?.toString() ?? '')

  const toPct = (text: string) => (text.trim() === '' ? null : Number(text))
  const invalid = [progression, probability].some((text) => {
    const n = toPct(text)
    return n !== null && (!Number.isInteger(n) || n < 0 || n > 100 || n % 5 !== 0)
  })

  const save = () => {
    updateStage.mutate({
      stage: stage.stage,
      patch: {
        name: name.trim(),
        progression_pct: toPct(progression),
        probability_pct: toPct(probability),
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
          <PctInput value={progression} onChange={setProgression} label="Progression %" />
        ) : (
          <Pct value={stage.progression_pct} />
        )}
      </td>
      <td>
        {editing ? (
          <PctInput value={probability} onChange={setProbability} label="Probability %" />
        ) : (
          <Pct value={stage.probability_pct} />
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
            <Button size="sm" onClick={save} disabled={invalid} title={invalid ? '0–100 in steps of 5' : undefined}>
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

function Pct({ value }: { value: number | null }) {
  return value === null ? <span className="text-muted-foreground">—</span> : <span className="tabular-nums">{value}%</span>
}

function PctInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <Input
      className="h-8 w-16"
      type="number"
      min={0}
      max={100}
      step={5}
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
