import { Fragment, useState } from 'react'
import { ChevronDownIcon, ChevronRightIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { ErrorBox, LoadingRow, Mono, Row, Table } from './shared'
import {
  typeLabel,
  useMetadataFields,
  useMetadataModules,
  useMetadataPicklists,
  type MetadataField,
  type MetadataPicklist,
} from '@/lib/metadata'

/**
 * Setup → Developer Space → API Names — the one screen that shows the names
 * code uses. Zoho keeps them in its developer area (APIs → API Names) and
 * nowhere in Modules and Fields; ARK does the same since the Setup rebuild,
 * step 4a (1 Oct 2026), when Setup stopped asking anyone to type one.
 *
 * Read-only, and unlike Zoho's it stays read-only for fields made in Setup
 * too: an api_name is the key every stored value is written under (a column,
 * or a key of the module's custom_fields), and the name conditions, formulas
 * and conversion mappings refer to. Renaming it would cut every existing record
 * off from its value while looking like it worked.
 *
 * Per module: the module's own key, then each field's label, API name, type,
 * where its value is stored, and its list of choices — which opens to show
 * each choice's stored value beside the label people see.
 */
export function ApiNamesTab() {
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()
  const { data: picklists = [] } = useMetadataPicklists()
  const [moduleKey, setModuleKey] = useState('leads')
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const { data: fields = [], isLoading: loadingFields } = useMetadataFields(moduleKey, 'all')

  if (isLoading) return <LoadingRow what="modules" />
  if (isError) return <ErrorBox error={error} />

  const term = search.trim().toLowerCase()
  const shown = (
    term
      ? fields.filter(
          (f) => f.label.toLowerCase().includes(term) || f.api_name.toLowerCase().includes(term)
        )
      : fields
  )
    .slice()
    .sort((a, b) => a.label.localeCompare(b.label))
  const listOf = (field: MetadataField) =>
    picklists.find((p) => p.picklist_key === field.picklist_key)

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          aria-label="Module"
          className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
          value={moduleKey}
          onChange={(e) => {
            setModuleKey(e.target.value)
            setOpen(null)
          }}
        >
          {modules.map((m) => (
            <option key={m.module_key} value={m.module_key}>
              {m.label}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground text-xs">
          Module API name <Mono>{moduleKey}</Mono>
        </span>
        <Input
          className="ml-auto h-9 w-64"
          placeholder="Search label or API name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loadingFields ? (
        <LoadingRow what="fields" />
      ) : (
        <Table
          head={
            <>
              <th className="w-8" />
              <th>Field label</th>
              <th>API name</th>
              <th className="w-40">Data type</th>
              <th className="w-36">Value stored in</th>
              <th>Choices</th>
            </>
          }
        >
          {shown.map((field) => {
            const list = listOf(field)
            const isOpen = open === field.placement_id
            return (
              <Fragment key={field.placement_id}>
                <Row muted={field.status === 'deleted'}>
                  <td>
                    {list && (
                      <button
                        type="button"
                        aria-label={isOpen ? 'Hide choices' : 'Show choices'}
                        className="text-muted-foreground hover:text-foreground"
                        onClick={() => setOpen(isOpen ? null : field.placement_id)}
                      >
                        {isOpen ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4" />}
                      </button>
                    )}
                  </td>
                  <td>
                    {field.label}
                    {field.status === 'deleted' && (
                      <Badge variant="outline" className="ml-2">
                        Unused
                      </Badge>
                    )}
                  </td>
                  <td>
                    <Mono>{field.api_name}</Mono>
                  </td>
                  <td>
                    {typeLabel(field.field_type)} <Mono>{field.field_type}</Mono>
                  </td>
                  <td className="text-xs">{storedIn(field)}</td>
                  <td>
                    {field.picklist_key ? (
                      <>
                        <Mono>{field.picklist_key}</Mono>
                        {list?.is_global && (
                          <Badge variant="secondary" className="ml-2">
                            Global set
                          </Badge>
                        )}
                      </>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </Row>
                {isOpen && list && <ChoiceRows list={list} />}
              </Fragment>
            )
          })}
        </Table>
      )}
    </>
  )
}

function storedIn(field: MetadataField): string {
  if (field.value_mode === 'read_through') return 'Nothing — shown from the parent'
  if (field.storage === 'custom_fields') return 'Custom field store'
  if (field.storage === 'column') return 'Its own column'
  return '—'
}

function ChoiceRows({ list }: { list: MetadataPicklist }) {
  return (
    <tr className="bg-muted/20 border-t">
      <td />
      <td colSpan={5} className="px-3 py-2">
        <table className="text-sm">
          <thead className="text-muted-foreground text-xs">
            <tr className="[&>th]:pr-6 [&>th]:pb-1 [&>th]:text-left [&>th]:font-medium">
              <th>Choice</th>
              <th>Stored value</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.values.map((value) => (
              <tr key={value.id} className={value.active ? undefined : 'text-muted-foreground'}>
                <td className="pr-6">{value.label}</td>
                <td className="pr-6">
                  <Mono>{value.key}</Mono>
                </td>
                <td className="text-xs">{value.active ? '' : 'Inactive'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </td>
    </tr>
  )
}
