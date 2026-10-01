import { useState } from 'react'
import { SearchIcon } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { FieldDialog } from './FieldDialog'
import { ErrorBox, LoadingRow, Row, Table } from './shared'
import { typeLabel, useMetadataFields, type MetadataField } from '@/lib/metadata'

/**
 * A module's Fields tab — Zoho's Field Listing (Setup rebuild, 4b, 1 Oct 2026):
 * a search over names and data types, and three columns, Fields · Data Type ·
 * Custom Field. A row opens the field's properties.
 *
 * It arranges nothing. This tab used to be a dense table with order arrows,
 * Required toggles, section headers and Delete — the same edits the layout
 * makes, in a second place. Zoho does all of that on the layout, and now so
 * does ARK: adding fields and sections, moving, marking required, removing.
 *
 * "Custom Field" is Zoho's word for a field made in Setup: its values live in
 * the module's custom field store rather than a column of its own.
 */
export function FieldsTab({ moduleKey }: { moduleKey: string }) {
  const { data: fields = [], isLoading, isError, error } = useMetadataFields(moduleKey, 'active')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<MetadataField | undefined>(undefined)

  if (isLoading) return <LoadingRow what="fields" />
  if (isError) return <ErrorBox error={error} />

  const term = search.trim().toLowerCase()
  const shown = fields
    .filter(
      (f) =>
        !term ||
        f.label.toLowerCase().includes(term) ||
        typeLabel(f.field_type).toLowerCase().includes(term)
    )
    .sort((a, b) => a.label.localeCompare(b.label))

  return (
    <>
      <span className="bg-accent text-foreground mb-3 inline-block rounded-full px-3 py-1 text-sm font-semibold">
        Field Listing
      </span>

      <div className="relative mb-3 w-80">
        <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
        <Input
          type="search"
          className="pl-8"
          placeholder="Search Fields or Data Types"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <Table
        head={
          <>
            <th>Fields</th>
            <th className="w-1/3">Data Type</th>
            <th className="w-40">Custom Field</th>
          </>
        }
      >
        {shown.map((field) => (
          <Row key={field.placement_id}>
            <td>
              <button
                type="button"
                className="text-left hover:underline"
                onClick={() => setEditing(field)}
              >
                {field.label}
              </button>
              {field.value_mode === 'read_through' && (
                <span className="text-muted-foreground ml-2 text-xs">From the Lead</span>
              )}
            </td>
            <td>{typeLabel(field.field_type)}</td>
            <td>{field.storage === 'custom_fields' ? 'Yes' : ''}</td>
          </Row>
        ))}
      </Table>
      {shown.length === 0 && (
        <p className="text-muted-foreground py-6 text-sm">No field matches “{search.trim()}”.</p>
      )}

      <FieldDialog
        open={Boolean(editing)}
        onOpenChange={(open) => !open && setEditing(undefined)}
        moduleKey={moduleKey}
        field={editing}
      />
    </>
  )
}
