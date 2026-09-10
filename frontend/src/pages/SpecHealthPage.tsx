import { specHealth } from '@/lib/spec/health'

/**
 * Gaps in the field register, read live from the spec.
 *
 * Deliberately plain: this is a worklist for the register correction pass
 * before POC-2, not a screen anybody demos. It is not the Feedback page.
 */
export function SpecHealthPage() {
  const groups = specHealth()
  const total = groups.reduce((n, g) => n + g.rows.length, 0)

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <h1 className="text-page-title font-bold">Spec health</h1>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {total} things the field register does not currently say. Each one is a question for the
        register correction pass — the engine does not guess at any of them.
      </p>

      {groups.length === 0 && (
        <p className="mt-6 text-sm text-muted-foreground">Nothing outstanding.</p>
      )}

      {groups.map((group) => (
        <section key={group.id} className="mt-8">
          <h2 className="text-base font-semibold">
            {group.title} <span className="text-muted-foreground">({group.rows.length})</span>
          </h2>
          <p className="mt-0.5 mb-2 text-sm text-muted-foreground">{group.ask}</p>

          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-label">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Module</th>
                  <th className="px-3 py-2 text-left font-medium">Field</th>
                  <th className="px-3 py-2 text-left font-medium">api_name</th>
                  <th className="px-3 py-2 text-left font-medium">Type</th>
                  <th className="px-3 py-2 text-left font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((row) => (
                  <tr key={`${group.id}:${row.ref}`} className="border-t align-top">
                    <td className="px-3 py-1.5 whitespace-nowrap">{row.module}</td>
                    <td className="px-3 py-1.5">{row.label}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{row.api_name}</td>
                    <td className="px-3 py-1.5 whitespace-nowrap">{row.type}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{row.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  )
}
