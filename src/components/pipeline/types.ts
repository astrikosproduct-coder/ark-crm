import type { ComponentType, ReactNode } from 'react'
import type { QueryClient } from '@tanstack/react-query'

import type { Stage, Transition } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'
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

  /** A transition writes the band midpoint into probability_pct. Leads do. */
  writesProbability: boolean

  /** Where a skip reason is written on the record, when the module has one. */
  skipReasonField?: string
  /** Where a reversal reason is written on the record. */
  reversalReasonField?: string

  /** Values ARK stamps on every save and every transition. */
  stamp: () => Values

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
}

export type PipelineSlot = ComponentType<{ ctx: PipelineRecordContext }>
