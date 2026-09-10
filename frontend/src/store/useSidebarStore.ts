import { create } from 'zustand'

const KEY = 'sidebar-collapsed'

function getInitial(): boolean {
  return localStorage.getItem(KEY) === '1'
}

interface SidebarState {
  collapsed: boolean
  toggleCollapsed: () => void
}

/**
 * Whether the left nav is the icon-only rail — ARK_brand_UI.md §2.2. Kept in a
 * store rather than component state so the choice survives a reload, the same
 * way the theme does.
 */
export const useSidebarStore = create<SidebarState>((set, get) => ({
  collapsed: getInitial(),
  toggleCollapsed: () => {
    const next = !get().collapsed
    localStorage.setItem(KEY, next ? '1' : '0')
    set({ collapsed: next })
  },
}))
