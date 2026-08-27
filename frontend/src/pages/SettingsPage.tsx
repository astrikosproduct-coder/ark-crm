import { useState } from 'react'
import { RotateCcw } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { date as fmtDate } from '@/lib/format'
import type { SeedStamp } from '@/lib/spec/seed'
import { useDataStore } from '@/store/useDataStore'

export function SettingsPage() {
  const reset = useDataStore((s) => s.reset)
  const queryClient = useQueryClient()
  const [justReset, setJustReset] = useState(false)

  // Read through MSW like everything else — CLAUDE.md rule 2 — even though the
  // stamp is written by the loader rather than by a user.
  // A store seeded before date rebasing existed has no stamp, and the endpoint
  // answers with the empty array every unknown collection gets.
  const { data: stamp } = useQuery({
    queryKey: ['collection', '__seed'],
    queryFn: async () => (await api.get<Partial<SeedStamp>>('/__seed')).data,
  })
  const seeded = stamp?.anchor_date ? (stamp as SeedStamp) : undefined

  const handleReset = () => {
    const confirmed = window.confirm(
      'This clears everything stored in this browser and reloads the original seed data. Continue?'
    )
    if (!confirmed) return

    reset()
    void queryClient.invalidateQueries()
    setJustReset(true)
    window.setTimeout(() => setJustReset(false), 2500)
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      <p className="text-muted-foreground mt-0.5 text-sm">
        Prototype-only controls. Nothing on this page exists in the real product.
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Reset demo data</CardTitle>
          <CardDescription>
            Clears every record created or edited in this browser and reloads the original seed
            data from the spec, re-anchored to today. This cannot be undone.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Every seeded date is fixed in the workbook, so the loader shifts
              the whole seed by today − anchor as it seeds. Shown here because a
              demo opening on stale dates is the failure it prevents, and
              because that only happens on first run and on a reset. */}
          {seeded ? (
            <p className="text-muted-foreground text-sm">
              Seed dates anchored to <span className="text-foreground">{fmtDate(seeded.anchor_date)}</span>,
              seeded on <span className="text-foreground">{fmtDate(seeded.seeded_on)}</span> and
              shifted by{' '}
              <span className="text-foreground">
                {seeded.delta_days >= 0 ? '+' : ''}
                {seeded.delta_days} days
              </span>
              . Reset to re-anchor to today.
            </p>
          ) : (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              This browser holds seed data from before date rebasing, so its registrations and
              other dated records are stale. Reset demo data to anchor them to today.
            </p>
          )}

          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={handleReset}>
              <RotateCcw className="size-4" />
              Reset demo data
            </Button>
            {justReset && <span className="text-muted-foreground text-sm">Demo data reset.</span>}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
