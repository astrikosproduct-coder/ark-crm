import { api } from '@/lib/api'

export type AutomationType =
  | 'email'
  | 'file_upload'
  | 'notification'
  | 'record_update'
  | 'webhook'
  | 'task'

export interface AutomationEntry {
  type: AutomationType
  /** What the automation would have acted on. */
  target: string
  /** One line, written as the automation would describe itself. */
  detail: string
  module?: string
  api_name?: string
}

/**
 * Record an automation that WOULD have fired.
 *
 * Nothing is sent, uploaded or scheduled anywhere — CLAUDE.md rule 6. The
 * entry goes to the automationLog collection through MSW like any other write,
 * so the dockable panel built in a later prompt reads it with no changes here.
 */
export async function logAutomation(entry: AutomationEntry): Promise<void> {
  try {
    await api.post('/automationLog', { ...entry, timestamp: new Date().toISOString() })
  } catch (error) {
    // The log is an observation of the prototype, never a precondition of it.
    console.error('[automation] could not write log entry', error)
  }
}
