import { CherryIcon, TrophyIcon, type LucideIcon } from 'lucide-react'

/**
 * The icon for each Opportunity priority pick: a Cherry for Low Hanging (the
 * business's own phrase, "low-hanging fruit") and a Trophy for Top 10.
 *
 * Keyed by the flag's api_name. Kept in its own module rather than in
 * lib/priorityFlags, which is plain data shared with the MSW handler, and
 * rather than beside the PriorityFlagMark component, so that file exports only
 * components and Fast Refresh keeps working on it.
 */
export const PRIORITY_ICONS: Record<string, LucideIcon> = {
  is_low_hanging: CherryIcon,
  is_top_10: TrophyIcon,
}
