import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DownloadIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { ErrorNotice } from '@/components/ui/notice'
import { downloadCsv } from '@/lib/csv'
import { type FeedbackItem, useFeedbackList, useIsDeveloper, useSetFeedbackStatus } from '@/lib/feedback'
import { dateTime } from '@/lib/format'
import { labelForValue, optionsFor } from '@/lib/spec'
import { cn } from '@/lib/utils'

const STATUS_PICKLIST = 'feedback__status'
const CATEGORY_PICKLIST = 'feedback__category'
const ALL = '__all__'

const STATUS_TONE: Record<string, string> = {
  NEW: 'bg-primary/15 text-primary',
  READ: 'bg-muted text-muted-foreground',
  DONE: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
}

/**
 * The feedback inbox — DEVELOPER only (UX roadmap item 2).
 *
 * The nav entry is shown to developers alone, but that is presentation: the
 * list comes from GET /api/feedback, which answers 403 to anyone else, and this
 * page says so rather than pretending the inbox is empty.
 *
 * Opening an item marks it Read; Done and New are one click. Hand-built for the
 * same reason as FeedbackButton — feedback is not a register module.
 */
export function FeedbackPage() {
  const isDeveloper = useIsDeveloper()
  const { data, isLoading, error } = useFeedbackList(true)
  const setStatus = useSetFeedbackStatus()
  const [statusFilter, setStatusFilter] = useState<string>('NEW')
  const [categoryFilter, setCategoryFilter] = useState<string>(ALL)
  const [openId, setOpenId] = useState<string | null>(null)

  const statuses = optionsFor(STATUS_PICKLIST)
  const categories = optionsFor(CATEGORY_PICKLIST)

  const items = useMemo(
    () =>
      (data?.items ?? []).filter(
        (item) =>
          // The item being read stays put: opening it marks it Read, and it
          // must not vanish from the New filter under the reader's cursor.
          item.id === openId ||
          ((statusFilter === ALL || item.status === statusFilter) &&
            (categoryFilter === ALL || item.category === categoryFilter))
      ),
    [data, statusFilter, categoryFilter, openId]
  )

  const open = (item: FeedbackItem) => {
    setOpenId(openId === item.id ? null : item.id)
    if (item.status === 'NEW') setStatus.mutate({ id: item.id, status: 'READ' })
  }

  const exportCsv = () =>
    downloadCsv(`ark-feedback-${new Date().toISOString().slice(0, 10)}.csv`, [
      ['ID', 'Sent', 'From', 'Category', 'Status', 'Page', 'Record', 'Message'],
      ...items.map((item) => [
        item.feedback_id,
        dateTime(item.created_at),
        item.created_by_name ?? item.created_by,
        labelForValue(CATEGORY_PICKLIST, item.category),
        labelForValue(STATUS_PICKLIST, item.status),
        item.page_path,
        item.record_ref,
        item.message,
      ]),
    ])

  const counts = useMemo(() => {
    const out: Record<string, number> = {}
    for (const item of data?.items ?? []) out[item.status] = (out[item.status] ?? 0) + 1
    return out
  }, [data])

  return (
    <PageLayout
      wide
      title="Feedback"
      actions={
        items.length > 0 && (
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <DownloadIcon className="size-4" />
            Export CSV
          </Button>
        )
      }
      tabs={[
        {
          key: 'inbox',
          label: 'Inbox',
          content: (
            <div className="space-y-3 py-3">
              {!isDeveloper && !error && (
                <p className="text-muted-foreground text-sm">Only developers can read feedback.</p>
              )}
              {error ? (
                <ErrorNotice error={error} />
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {[{ key: ALL, label: 'All' }, ...statuses].map((option) => (
                      <Button
                        key={option.key}
                        type="button"
                        size="sm"
                        variant={statusFilter === option.key ? 'default' : 'outline'}
                        onClick={() => setStatusFilter(option.key)}
                      >
                        {option.label}
                        {option.key !== ALL && counts[option.key] ? (
                          <span className="tabular-nums opacity-70">{counts[option.key]}</span>
                        ) : null}
                      </Button>
                    ))}
                    <span className="bg-border mx-1 h-5 w-px" aria-hidden />
                    {[{ key: ALL, label: 'Any kind' }, ...categories].map((option) => (
                      <Button
                        key={option.key}
                        type="button"
                        size="sm"
                        variant={categoryFilter === option.key ? 'outline' : 'ghost'}
                        onClick={() => setCategoryFilter(option.key)}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>

                  <div className="bg-card overflow-x-auto rounded-lg shadow-sm">
                    <table className="w-full border-separate border-spacing-0 text-sm">
                      <thead className="text-label text-muted-foreground text-left">
                        <tr>
                          <th className="border-b px-4 py-2 font-semibold">Status</th>
                          <th className="border-b px-4 py-2 font-semibold">Feedback</th>
                          <th className="border-b px-4 py-2 font-semibold">Kind</th>
                          <th className="border-b px-4 py-2 font-semibold">From</th>
                          <th className="border-b px-4 py-2 font-semibold whitespace-nowrap">Sent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {isLoading && (
                          <tr>
                            <td colSpan={5} className="text-muted-foreground px-4 py-8 text-center">
                              Loading…
                            </td>
                          </tr>
                        )}
                        {!isLoading && items.length === 0 && (
                          <tr>
                            <td colSpan={5} className="text-muted-foreground px-4 py-8 text-center">
                              {data?.items.length ? 'Nothing matches these filters.' : 'No feedback yet.'}
                            </td>
                          </tr>
                        )}
                        {items.map((item) => {
                          const expanded = openId === item.id
                          return (
                            <tr
                              key={item.id}
                              tabIndex={0}
                              onClick={() => open(item)}
                              onKeyDown={(e) => e.key === 'Enter' && open(item)}
                              className="hover:bg-accent focus-visible:bg-accent cursor-pointer align-top outline-none even:bg-raised/60"
                            >
                              <td className="px-4 py-2">
                                <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', STATUS_TONE[item.status])}>
                                  {labelForValue(STATUS_PICKLIST, item.status)}
                                </span>
                              </td>
                              <td className="max-w-xl px-4 py-2">
                                <p className={cn('whitespace-pre-wrap', !expanded && 'line-clamp-2')}>{item.message}</p>
                                {expanded && (
                                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs" onClick={(e) => e.stopPropagation()}>
                                    {item.page_path && (
                                      <Link to={item.page_path} className="text-link hover:underline">
                                        Open the page it was sent from
                                      </Link>
                                    )}
                                    <span className="ml-auto flex gap-1.5">
                                      {item.status !== 'DONE' && (
                                        <Button size="sm" variant="outline" onClick={() => setStatus.mutate({ id: item.id, status: 'DONE' })}>
                                          Mark done
                                        </Button>
                                      )}
                                      {item.status !== 'NEW' && (
                                        <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: item.id, status: 'NEW' })}>
                                          Mark as new
                                        </Button>
                                      )}
                                    </span>
                                  </div>
                                )}
                              </td>
                              <td className="px-4 py-2 whitespace-nowrap">{labelForValue(CATEGORY_PICKLIST, item.category)}</td>
                              <td className="px-4 py-2 whitespace-nowrap">{item.created_by_name ?? '—'}</td>
                              <td className="text-muted-foreground px-4 py-2 whitespace-nowrap">{dateTime(item.created_at)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  {setStatus.isError && <ErrorNotice error={setStatus.error} />}
                </>
              )}
            </div>
          ),
        },
      ]}
    />
  )
}
