import { Badge } from '@/components/ui/badge'
import { ErrorBox, LoadingRow, MetadataIntro, Mono, Row, Table } from './shared'
import { useConversionMappings, type ConversionMappingRow } from '@/lib/metadata'

/**
 * Conversion Mapping — what each conversion copies (metadata v2, 24 Sep 2026).
 *
 * Zoho's "Lead Conversion Mapping", READ-ONLY for now. The rows were written
 * by metadata_v2.py from what conversion already did, and conversion reads
 * them (app/carry_forward.py, app/progression.py). The screen that edits them
 * is built once, in its final place, with the Setup rebuild:
 * Setup → Customization → Modules and Fields → Leads / Opportunities →
 * Conversion Mapping.
 *
 * A field shown live "from the Lead" is not here: it is never copied. It is a
 * read-only item on the later module's layout (Fields tab).
 */

const PATHS: { path: ConversionMappingRow['path']; title: string; lead: string }[] = [
  {
    path: 'lead_to_opportunity',
    title: 'Lead → Opportunity',
    lead: 'Nothing is copied. The Opportunity shows the Lead’s fields live, in From the Lead.',
  },
  {
    path: 'opportunity_to_deal',
    title: 'Opportunity → Deal',
    lead: 'Copied once when the Deal is created. The Deal owns the value from then on.',
  },
  {
    path: 'lead_to_deal_pilot',
    title: 'Lead → Deal (paid pilot)',
    lead: 'When a pilot is marked Paid, its Deal is created from the Lead. These rows carry the Won rule, so they are locked.',
  },
]

const MODULE_LABEL: Record<string, string> = {
  leads: 'Lead',
  opportunities: 'Opportunity',
  deals: 'Deal',
}

const TRANSFORM_LABEL: Record<string, string> = {
  paid_poc_name: 'adds “ — Paid POC”',
}

export function ConversionMappingTab() {
  const { data: rows = [], isLoading, isError, error } = useConversionMappings()

  if (isLoading) return <LoadingRow what="conversion mapping" />
  if (isError) return <ErrorBox error={error} />

  return (
    <>
      <MetadataIntro>
        What each conversion copies onto the new record. A field shown from the Lead is never copied —
        it is shown live. This list is read-only until Setup gives it an editing screen.
      </MetadataIntro>

      {PATHS.map(({ path, title, lead }) => {
        const own = rows.filter((r) => r.path === path)
        const copies = own.filter((r) => r.kind === 'copy')
        const system = own.filter((r) => r.kind === 'system')
        return (
          <section key={path} className="mb-5">
            <h3 className="text-section text-xs font-bold tracking-wide">{title.toUpperCase()}</h3>
            <p className="text-muted-foreground mb-2 text-xs">{lead}</p>
            <Table
              head={
                <>
                  <th>From</th>
                  <th className="w-8" />
                  <th>To</th>
                  <th className="w-40">How</th>
                  <th className="w-24" />
                </>
              }
            >
              {copies.map((row) => (
                <Row key={row.id} muted={row.locked}>
                  <td>
                    <div className="font-medium">
                      {MODULE_LABEL[row.source_module ?? ''] ?? row.source_module} ·{' '}
                      {row.source_label ?? row.source_api_name}
                    </div>
                    <Mono>{row.source_api_name}</Mono>
                  </td>
                  <td className="text-muted-foreground">→</td>
                  <td>
                    <div className="font-medium">
                      {MODULE_LABEL[row.target_module] ?? row.target_module} ·{' '}
                      {row.target_label ?? row.target_api_name}
                    </div>
                    <Mono>{row.target_api_name}</Mono>
                  </td>
                  <td className="text-xs">
                    {row.transform ? TRANSFORM_LABEL[row.transform] ?? row.transform : 'copied as is'}
                  </td>
                  <td className="text-right">
                    {row.locked && <Badge variant="outline">Locked</Badge>}
                  </td>
                </Row>
              ))}
              {system.map((row) => (
                <Row key={row.id} muted>
                  <td className="text-xs italic">Set by the CRM</td>
                  <td>→</td>
                  <td>
                    <div>
                      {MODULE_LABEL[row.target_module] ?? row.target_module} ·{' '}
                      {row.target_label ?? row.target_api_name}
                    </div>
                    <Mono>{row.target_api_name}</Mono>
                  </td>
                  <td className="text-xs">{row.note}</td>
                  <td className="text-right">
                    <Badge variant="outline">System</Badge>
                  </td>
                </Row>
              ))}
            </Table>
          </section>
        )
      })}
    </>
  )
}
