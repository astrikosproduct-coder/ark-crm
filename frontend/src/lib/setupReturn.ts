/**
 * Where Setup's back arrow goes: the last page outside Setup (Zoho's ← on
 * Setup's home returns to where you were). Kept in memory for the tab's life —
 * a reload inside Setup goes back to the Dashboard.
 */
let lastAppPath = '/dashboard'

export function rememberAppPath(path: string): void {
  lastAppPath = path
}

export function appReturnPath(): string {
  return lastAppPath
}

export function isSetupPath(pathname: string): boolean {
  return pathname === '/setup' || pathname.startsWith('/setup/')
}
