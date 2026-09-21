import type { ComponentType, ReactNode } from 'react'
import type { QueryClient } from '@tanstack/react-query'

import type { Stage, Transition } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'
import type { FieldSpec } from '@/types/field'
import type { ResolvedRecord } from '@/lib/spec/resolveRecord'

/**
 * One pipeline module, as far as the shared record page is concerned.
 *
 * Leads and Deals were two 430-line files that differed in about forty places
 * and agreed in the other four hundred. Adding Opportunities as a third copy
 * would have tripled a screen nobody could safely change. What is left here is
 * exactly the set of things that genuinely differ between modules — everything
 * described as data, everything that is really different JSX handed over as a
 * slot component.
 *
 * A new pipeline module is a descriptor plus its own slots. It is not a new
 * page.
 */
export interface PipelineModuleSpec {
  /** Register module — drives every field lookup. */
  module: string
  /** Store collection behind /api. */
  collection: string
  /** Route prefix, for links to this module's records. */
  basePath: string
  /** Singular, lower case: "lead", "deal". Used in prose. */
  noun: string

  /**
   * The stages this module's rail draws, in order.
   *
   * stagesFor(module) from the split — Leads 0-3, Opportunities 4-6, Deals
   * 7-9. All three descriptors turned this knob when their own conversion
   * step was built (LeadDetailPage's Move to Opportunity's Module being the
   * last of the three); nothing here still draws the pre-split 0-7 / 8-9.
   */
  stages: Stage[]

  /** The leads_stage / deals__deal_stage key for a stage number. */
  stageKeyOf: (stage: number) => string | undefined

  /** Where a skip reason is written on the record, when the module has one. */
  skipReasonField?: string
  /** Where a reversal reason is written on the record. */
  reversalReasonField?: string

  /*
   * `stamp: () => Values` used to live here — the browser's own
   * modified_date/modified_by, merged into every save.
   *
   * It is gone because the server stamps both from the Entra session and its
   * own clock and ignores whatever the payload claims (app/routers/leads.py,
   * SYSTEM_STAMPED). A client-side stamp would now be a value that travels,
   * gets discarded, and misleads the next person reading this file into
   * thinking the browser decides who edited a record. It does not, and that is
   * the entire point: the two fields a manager most needs to trust are the two
   * a BD must not be able to write.
   */

  /**
   * Heading over the Current-stage tab's own content — "Lead Information",
   * "Opportunity Information", "Deal Information".
   *
   * It used to read "Stage 1 — Demo Presentation", which was the name of the
   * section drawn immediately underneath it: the same words twice, one inside
   * the other. This names the RECORD, the way Zoho's record pages do, and
   * leaves naming the stage to the section that holds the stage's fields.
   */
  recordHeading: string

  /** Heading over the non-stage sections on the Details tab. */
  detailsHeading: string

  /** Show the register's probability band on the stage line. */
  showProbabilityBand: boolean

  /** Tab order, left to right. */
  tabs: PipelineTab[]

  /** True when the record is finished and reads as history. */
  isReadOnly?: (values: Values) => boolean

  /** Extra spans on the header's metadata line, after id / client / partner. */
  Header?: PipelineSlot
  /** Buttons in the top-right. Replaces the default Advance button entirely. */
  Actions?: PipelineSlot
  /** A full-width notice between the header and the stage line. */
  Banner?: PipelineSlot
  /** The Related tab's contents. */
  Related?: PipelineSlot
  /**
   * Rendered under the stage's own form on the Current-stage tab, for a table
   * that belongs to a stage but not to this record's fields — Deals' Stage 8
   * payment milestones, whose rows live on the parent Opportunity. It is
   * handed the context and decides for itself which stages it draws on.
   */
  StagePanel?: PipelineSlot
  /** Dialogs and anything else rendered at page level. */
  Extras?: PipelineSlot

  /**
   * A logic-only component mounted inside the Current-stage editor's form
   * context for the given stage — rendered nowhere else, returns null, exists
   * to call useRecordForm() and react to a field changing while the user is
   * still typing (see LeadSegmentSync). Undefined for every stage that has no
   * such wiring, which is every stage of every module except Leads' Stage 0.
   */
  sideEffectsForStage?: (stage: number) => ReactNode
  /**
   * Runs once the Current-stage editor for the given stage has saved
   * successfully, handed the saved record and the query client so it can
   * write to and invalidate a DIFFERENT record's data — a save-time gap-fill
   * onto a linked record, never a mid-keystroke one. Undefined for every
   * stage that has no such wiring.
   */
  afterSaveForStage?: (
    stage: number
  ) => ((record: Record<string, unknown>, queryClient: QueryClient) => void | Promise<void>) | undefined
}

export type PipelineTab = 'current' | 'details' | 'history' | 'related'

/** What every slot is handed. Slots are components, so they may use hooks. */
export interface PipelineRecordContext {
  spec: PipelineModuleSpec
  /** The record id from the route. Empty only before it resolves. */
  id: string
  /** The EFFECTIVE record — stored values with inherited ones merged over. */
  values: Values | undefined
  resolved: ResolvedRecord
  /** The stage the record is at. */
  currentStage: number
  /** The stage the rail has selected, which is what the form below shows. */
  stageToShow: number
  isLoading: boolean
  /** The record is finished and must not be edited. */
  readOnly: boolean
  /** The End Client account, when one is set and loaded. */
  endClient: Values | undefined
  /** The Customer (Partner / SI) account. */
  partner: Values | undefined
  transitions: Transition[] | undefined
  /** Open the stage-change dialog. */
  openAdvance: () => void
  selectStage: (stage: number) => void
  setActiveTab: (tab: PipelineTab) => void
  /**
   * Drill down from a readiness criterion to the field that proves it: selects
   * the field's stage, switches to the tab and section that hold it, opens
   * that section for editing, then scrolls to and pulses the field. Handed to
   * every readiness surface — the drawer, the generic Update Stage dialog, and
   * any module's own Actions slot that embeds its own advance dialog, such as
   * LeadAdvanceDialog — so a criterion behaves identically wherever it is met.
   */
  jumpToField: (field: FieldSpec) => void
}

export type PipelineSlot = ComponentType<{ ctx: PipelineRecordContext }>
