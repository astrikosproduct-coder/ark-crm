import { createContext, useContext } from 'react'

/**
 * What a page may hand the app shell (Release 1.2, the Zoho list screen):
 * a place in the top bar for its title, and a request to be exactly one screen
 * tall, so its records box scrolls instead of the page. Only ListPageLayout
 * uses either; every other screen leaves both alone and scrolls as it always has.
 */
export interface ShellSlots {
  /** The top bar's title spot; null until the bar has mounted. */
  titleSlot: HTMLElement | null
  setTitleSlot: (el: HTMLElement | null) => void
  setFillScreen: (fill: boolean) => void
}

export const ShellSlotsContext = createContext<ShellSlots>({
  titleSlot: null,
  setTitleSlot: () => {},
  setFillScreen: () => {},
})

export const useShellSlots = () => useContext(ShellSlotsContext)

/**
 * A list page's toolbar line, for a view's own control — the Kanban board's
 * View Settings. Null outside a list page, where the control draws itself in place.
 */
export const ListToolbarSlot = createContext<HTMLElement | null>(null)
export const useListToolbarSlot = () => useContext(ListToolbarSlot)
