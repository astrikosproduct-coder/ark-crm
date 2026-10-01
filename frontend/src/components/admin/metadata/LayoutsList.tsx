import { Link } from 'react-router-dom'

import { date as fmtDate } from '@/lib/format'
import { useMetadataLayouts } from '@/lib/metadata'
import { ErrorBox, LoadingRow, Row, StatusSwitch, Table } from './shared'

/**
 * A module's Layout tab — Zoho's list of layouts (Setup rebuild, 4b, 1 Oct
 * 2026): Name · Shared To · Last Modified · Status, the name opening the
 * layout editor.
 *
 * ARK has one layout per module, "Standard" (metadata v2, 0038). Zoho's
 * "Create New Layout" and real sharing come with profiles (Item 4), so there
 * is no create button, Shared To says Everyone, and Status is on and fixed —
 * a module's only layout cannot be switched off.
 */
export function LayoutsList({
  moduleKey,
  layoutHref,
}: {
  moduleKey: string
  layoutHref: (layoutId: number) => string
}) {
  const { data: layouts = [], isLoading, isError, error } = useMetadataLayouts(moduleKey)

  if (isLoading) return <LoadingRow what="layouts" />
  if (isError) return <ErrorBox error={error} />

  return (
    <>
      <p className="text-muted-foreground mb-3 text-sm">
        The layout is the form people fill in for this module. Open it to arrange its sections
        and fields.
      </p>
      <Table
        head={
          <>
            <th>Name</th>
            <th>Shared To</th>
            <th className="w-48">Last Modified</th>
            <th className="w-24">Status</th>
          </>
        }
      >
        {layouts.map((layout) => (
          <Row key={layout.id}>
            <td>
              <Link to={layoutHref(layout.id)} className="text-link font-medium hover:underline">
                {layout.label}
              </Link>
            </td>
            <td>Everyone</td>
            <td>{layout.last_modified ? fmtDate(layout.last_modified) : '—'}</td>
            <td>
              <StatusSwitch
                checked
                disabled
                label={`${layout.label} is on`}
                title="A module's only layout is always on"
              />
            </td>
          </Row>
        ))}
      </Table>
    </>
  )
}
