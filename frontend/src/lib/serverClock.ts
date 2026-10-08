import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { companyDayKey } from '@/lib/time'

interface ClockResponse {
  now: string
  today: string
  timezone: string
  timezone_label: string
}

/** Where the server's clock stood against this page's monotonic clock. */
interface Anchor {
  /** The server's instant, in epoch ms, at `perfAt`. */
  serverMs: number
  /** performance.now() at that moment — elapsed time, never the laptop's wall clock. */
  perfAt: number
  label: string
}

/** How often the page re-reads the server's time; drift in between is negligible. */
const RESYNC_MS = 10 * 60 * 1000

/**
 * The server's time (28 Sep 2026). The instant comes from GET /api/clock — the
 * backend's clock, the one every record is stamped with. Between re-reads it
 * advances by performance.now(), which measures elapsed time and ignores the
 * laptop's date, time and zone settings, so a laptop set wrong still shows the
 * server's. Half the request's round trip is added, so the reading is when the
 * answer was written, not when it arrived.
 */
function useAnchor(): Anchor | undefined {
  const { data } = useQuery({
    queryKey: ['server-clock'],
    queryFn: async (): Promise<Anchor> => {
      const sent = performance.now()
      const { data } = await api.get<ClockResponse>('/clock')
      const received = performance.now()
      return { serverMs: Date.parse(data.now) + (received - sent) / 2, perfAt: received, label: data.timezone_label }
    },
    refetchInterval: RESYNC_MS,
    staleTime: RESYNC_MS,
  })
  return data
}

const serverNow = (anchor: Anchor) => anchor.serverMs + (performance.now() - anchor.perfAt)

/** The server's instant, re-rendering every second — for the top bar's clock only. */
export function useServerClock(): { now: number; label: string } | null {
  const anchor = useAnchor()
  const [, tick] = useState(0)

  useEffect(() => {
    // Wake on the next whole second, then every second, so the display turns over on time.
    let interval: ReturnType<typeof setInterval> | undefined
    const timeout = setTimeout(() => {
      tick((n) => n + 1)
      interval = setInterval(() => tick((n) => n + 1), 1000)
    }, 1000 - (performance.now() % 1000))
    return () => {
      clearTimeout(timeout)
      if (interval) clearInterval(interval)
    }
  }, [])

  return anchor ? { now: serverNow(anchor), label: anchor.label } : null
}

/** How often the day is re-checked. It re-renders only when the day changes. */
const DAY_CHECK_MS = 30 * 1000

/**
 * The server's company-calendar day, 'YYYY-MM-DD', or null until it is known.
 * A query keyed on it refetches when the day turns — which is how an open
 * dashboard moves into a new quarter or fiscal year at midnight IST without a
 * reload. Checked every 30 seconds; the state only changes when the day does.
 */
export function useServerDay(): string | null {
  const anchor = useAnchor()
  const [day, setDay] = useState<string | null>(null)

  useEffect(() => {
    if (!anchor) return
    const check = () => setDay(companyDayKey(new Date(serverNow(anchor))))
    check()
    const interval = setInterval(check, DAY_CHECK_MS)
    return () => clearInterval(interval)
  }, [anchor])

  return day
}
