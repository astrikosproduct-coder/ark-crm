import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { NumericInput } from '@/components/ui/numeric-input'
import { CreateNewDialog } from '@/components/form/CreateNewDialog'
import { FormSection } from '@/components/form/RecordForm'
import { RecordFormProvider, useRecordForm } from '@/hooks/useRecordForm'
import { fieldsOf, modules, sectionsFor } from '@/lib/spec'
import { computedOrder } from '@/lib/spec/formula'
import { validateForTransition } from '@/lib/spec/validation'
import { humanize } from '@/lib/format'
import type { FieldSpec } from '@/types/field'

/**
 * A harness for the form engine, not a module screen. It renders whatever the
 * spec says for the module you pick, so a reviewer can add a field to
 * spec/fields.json and watch it appear without a code change.
 */
export function FormEnginePage() {
  const [module, setModule] = useState('leads')
  const [mode, setMode] = useState<'view' | 'edit'>('edit')

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-page-title font-bold">Form engine</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Every field, section and rule below is read from spec/fields.json and
            spec/extensions.json. Nothing here is hardcoded.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Select value={module} onValueChange={setModule}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {modules.map((m) => (
                <SelectItem key={m} value={m}>
                  {humanize(m)} ({fieldsOf(m).length})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button
            variant="outline"
            onClick={() => setMode((m) => (m === 'edit' ? 'view' : 'edit'))}
          >
            {mode === 'edit' ? 'View mode' : 'Edit mode'}
          </Button>
        </div>
      </div>

      {/* Remount on module change so the record state starts clean. */}
      <RecordFormProvider key={`${module}:${mode}`} module={module} mode={mode}>
        <EngineBody module={module} />
      </RecordFormProvider>
    </div>
  )
}

function EngineBody({ module }: { module: string }) {
  const form = useRecordForm()
  const [creatingFor, setCreatingFor] = useState<FieldSpec | null>(null)
  const [transition, setTransition] = useState({ from: 0, to: 1 })

  const sections = useMemo(() => sectionsFor(module), [module])
  const order = useMemo(() => computedOrder(module), [module])

  const blockers = useMemo(
    () => validateForTransition(module, form.values, transition),
    [module, form.values, transition]
  )

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {sections.map((section) => (
          <FormSection
            key={section}
            module={module}
            section={section}
            onCreateNew={setCreatingFor}
            defaultOpen={section === sections[0]}
          />
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border p-4">
          <h2 className="text-sm font-semibold">Payload</h2>
          <p className="mb-2 text-xs text-muted-foreground">
            What a save would send. Computed values are snapshotted in.
          </p>
          <pre className="max-h-72 overflow-auto rounded-md bg-muted p-3 text-xs">
            {JSON.stringify(form.toPayload(), null, 2)}
          </pre>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border p-4">
            <h2 className="text-sm font-semibold">Transition check (layer 1)</h2>
            <p className="mb-2 text-xs text-muted-foreground">
              Mandatory fields only. Exit criteria, entry criteria and gates are layers 2 to 4.
            </p>
            <div className="mb-3 flex items-center gap-2 text-sm">
              <span>Stage</span>
              <NumericInput
                value={transition.from}
                onValueChange={(v) => setTransition((t) => ({ ...t, from: v === '' ? 0 : v }))}
                className="h-8 w-14 px-2"
              />
              <span>to</span>
              <NumericInput
                value={transition.to}
                onValueChange={(v) => setTransition((t) => ({ ...t, to: v === '' ? 0 : v }))}
                className="h-8 w-14 px-2"
              />
              {transition.to - transition.from > 1 && <Badge variant="warning">skip</Badge>}
            </div>
            {blockers.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing blocks this move.</p>
            ) : (
              <>
                <p className="mb-1 text-sm">
                  <span className="font-medium">{blockers.length}</span> fields block it:
                </p>
                <ul className="max-h-48 space-y-0.5 overflow-auto text-xs text-muted-foreground">
                  {blockers.map((b) => (
                    <li key={b.api_name}>
                      <span className="text-foreground">{b.label}</span> — {b.message}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <div className="rounded-lg border p-4">
            <h2 className="text-sm font-semibold">Computed evaluation order</h2>
            <p className="mb-2 text-xs text-muted-foreground">
              Topologically sorted, so a formula never reads a stale input.
            </p>
            {order.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No executable formulas in this module.
              </p>
            ) : (
              <ol className="space-y-0.5 text-xs">
                {order.map((name, i) => (
                  <li key={name}>
                    <span className="text-muted-foreground">{i + 1}.</span> {name}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </div>

      <CreateNewDialog
        field={creatingFor}
        onClose={() => setCreatingFor(null)}
        onCreated={(id) => {
          if (creatingFor) form.setValue(creatingFor.api_name, id)
        }}
      />
    </div>
  )
}
