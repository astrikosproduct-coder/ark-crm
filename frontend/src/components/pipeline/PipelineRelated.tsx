import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'
import { dealListCell } from '@/components/deals/dealListCell'
import { leadListCell } from '@/components/leads/leadListCell'
import { opportunityListCell } from '@/components/opportunities/opportunityListCell'
import { registrationListCell } from '@/components/partners/registrationListCell'
import type { PipelineRecordContext } from '@/components/pipeline/types'
import { PursuitGroupPanel } from '@/components/pursuits/PursuitGroupPanel'
import { ComingSoon } from '@/pages/ComingSoon'
import { displayNameOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

/**
 * The Related tab of a pipeline record: everything the register points at this
 * record FROM somewhere else.
 *
 * WHAT DECIDES THE SECTION LIST
 * -----------------------------
 * Not taste — the register's own lookups. Every module carrying a lookup whose
 * target is this record earns a section:
 *
 *   contacts.account            -> the two party accounts (below)
 *   partners.linked_lead        -> Deal Registration
 *   *.pursuit_group             -> Pursuit Group (every partner's pursuit of
 *                                  this same project; see PursuitGroupPanel)
 *   leads.parent_deal           -> Expansion leads
 *   opportunities.parent_lead   -> the Opportunity this Lead became
 *   deals.parent_lead           -> a Deal converted straight from the Lead
 *   deals.parent_opportunity    -> the Deal an Opportunity became
 *   quotes.lead                 -> Quotes
 *   bids_pocs.GATE.parent_lead  -> Gates
 *   bids_pocs.BID.lead          -> Bid
 *   bids_pocs.POC.lead          -> POC / Pilot
 *
 * BOTH PARTIES, NOT ONE
 * ---------------------
 * CLAUDE.md's two-party rule: "End Client and Customer (Partner / SI) are
 * different organisations on the same deal." This tab listed the End Client's
 * contacts and silently omitted the partner's, so on a partner-sourced pursuit
 * the people actually being dealt with every day were the ones the screen did
 * not show. Both are drawn now, each labelled with the role the account plays,
 * because "Contacts" over a single unlabelled list is what let one party stand
 * in for both in the first place.
 *
 * Pre-Bid Alliance Partner is deliberately NOT a third panel. It is a third,
 * separate field — the partner who SOURCED a deal is not always the partner you
 * BID with — and giving it equal billing in a contacts tab would suggest a
 * working relationship with its people that the field does not claim.
 *
 * THE UNBUILT SECTIONS ARE NAMED, NOT HIDDEN
 * ------------------------------------------
 * Quotes, Gates, Bid and POC / Pilot have a real lookup pointing here and no
 * `list_views` entry to render one with, so each draws its heading and its
 * description exactly like a built section and a "Coming in a later phase" box
 * where its table will go. Hiding them instead would make the tab look
 * complete, and the whole point of this build is to show BD the shape of the
 * record so they can tell us what is missing — a named gap is reviewable, an
 * absent one is invisible.
 *
 * ONE COMPONENT, THREE MODULES
 * ----------------------------
 * Leads, Opportunities and Deals render this, each getting the sections its own
 * links support. Written once for the reason PipelineRecordPage itself was: the
 * Lead and Deal versions were already separate copies that had drifted — one
 * offered "Add contact" and the other did not, and their empty states were
 * worded differently.
 */
export function PipelineRelated({
  ctx,
  children,
}: {
  ctx: PipelineRecordContext
  children?: ReactNode
}) {
  if (!ctx.values) return null

  const module = ctx.spec.module
  const endClientId = idOf(ctx.values.end_client)
  const partnerId = idOf(ctx.values.customer_partner_si)

  /**
   * The Lead at the head of this chain — this record when it IS a Lead, its
   * parent otherwise.
   *
   * A registration points at a Lead and at nothing else (`linked_lead` is its
   * only pipeline lookup), so an Opportunity or a Deal finds its registration
   * through the Lead it descends from. `values` is the EFFECTIVE record with
   * read-through values merged in, which is why parent_lead resolves here on
   * an Opportunity and a Deal alike.
   */
  const leadId = module === 'leads' ? ctx.id : idOf(ctx.values.parent_lead)

  // The register does not stop the same account being named as both, and on a
  // pursuit where it has been, two identical lists under two different headings
  // would read as two sets of people. One panel, both roles named.
  const oneOrganisation = Boolean(endClientId) && endClientId === partnerId

  return (
    <div className="space-y-8">
      <ContactPanel
        role={oneOrganisation ? 'End Client and Customer (Partner / SI)' : 'End Client'}
        accountId={endClientId}
        account={ctx.endClient}
        unsetMessage="No End Client set on this record yet."
      />

      {!oneOrganisation && (
        <ContactPanel
          role="Customer (Partner / SI)"
          accountId={partnerId}
          account={ctx.partner}
          unsetMessage="No Customer (Partner / SI) on this record — not captured yet."
        />
      )}

      <PursuitGroupPanel ctx={ctx} />

      <RelatedSection
        title="Deal Registration"
        description={
          leadId
            ? 'Raised in Partners, and claimed against this pursuit.'
            : 'No parent Lead on this record, so no registration can be traced to it.'
        }
      >
        {leadId && (
          <EmbeddedList
            module="registrations"
            basePath="/partners/registrations"
            filter={{ linked_lead: leadId }}
            hiddenColumns={['linked_lead']}
            renderCell={registrationListCell}
            emptyMessage="No partner has registered this deal."
          />
        )}
      </RelatedSection>

      {module === 'leads' && (
        <RelatedSection
          title="Opportunity"
          description="What this Lead became when it crossed into Stage 4."
        >
          <EmbeddedList
            module="opportunities"
            basePath="/opportunities"
            filter={{ parent_lead: ctx.id }}
            hiddenColumns={['parent_lead']}
            renderCell={opportunityListCell}
            emptyMessage="This Lead has not been converted yet."
          />
        </RelatedSection>
      )}

      {/* A Lead gets BOTH downstream sections, not one. The split put
          Opportunities between Leads and Deals, but a Lead can still convert
          straight to a Deal — DEAL-00001 does exactly that, carrying
          parent_lead with parent_opportunity empty — so a tab that only
          listed Opportunities would show nothing for the one conversion that
          has actually happened. */}
      {module === 'leads' && (
        <RelatedSection
          title="Deal"
          description="A Deal converted directly from this Lead, without an Opportunity in between."
        >
          <EmbeddedList
            module="deals"
            basePath="/deals"
            filter={{ parent_lead: ctx.id }}
            hiddenColumns={['parent_lead']}
            renderCell={dealListCell}
            emptyMessage="No Deal has been converted directly from this Lead."
          />
        </RelatedSection>
      )}

      {module === 'opportunities' && (
        <RelatedSection
          title="Deal"
          description="What this Opportunity became when it was won at Stage 7."
        >
          <EmbeddedList
            module="deals"
            basePath="/deals"
            filter={{ parent_opportunity: ctx.id }}
            hiddenColumns={['parent_opportunity']}
            renderCell={dealListCell}
            emptyMessage="This Opportunity has not been converted yet."
          />
        </RelatedSection>
      )}

      {module === 'deals' && (
        <RelatedSection
          title="Expansion leads"
          description="New pursuits opened off this Deal at Stage 9 — Expansion."
        >
          <EmbeddedList
            module="leads"
            basePath="/leads"
            filter={{ parent_deal: ctx.id }}
            hiddenColumns={['parent_deal']}
            renderCell={leadListCell}
            emptyMessage="No expansion pursuit has been opened off this Deal."
          />
        </RelatedSection>
      )}

      {/* The four the register describes and nothing renders yet. Each one has
          a live lookup pointing at this record; what none of them has is a
          `list_views` entry saying which columns a reader should see. */}
      <RelatedSection
        title="Quotes"
        description="Priced quotes raised against this pursuit, at price book rev4."
      >
        <ComingSoon label="Quotes" />
      </RelatedSection>

      <RelatedSection
        title="Gates"
        description="G1 POC Brief, G2 Commit to Bid and G3 Commercial — each anchored to the ENTRY of a stage, so a skip cannot bypass one."
      >
        <ComingSoon label="The three gates" />
      </RelatedSection>

      <RelatedSection
        title="Bid"
        description="The bid record and its checklist, for a pursuit that went through an RFP."
      >
        <ComingSoon label="The bid record" />
      </RelatedSection>

      <RelatedSection
        title="POC / Pilot"
        description="The POC record and its signatories. The POC workspace — weekly logs, issue register, close-out report — is out of scope."
      >
        <ComingSoon label="The POC record" />
      </RelatedSection>

      {children}
    </div>
  )
}

/** A lookup stores a record id; anything else is not one. */
function idOf(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

/**
 * One block of the tab: a heading, a line saying what it holds, an optional
 * action, and a body that is either a table or a placeholder.
 *
 * The heading and description are drawn the SAME WAY whether the body is real
 * or not, which is the point — a reviewer scanning the tab reads one list of
 * what belongs on this record, not a built half and a missing half in two
 * different visual languages.
 */
function RelatedSection({
  title,
  description,
  action,
  children,
}: {
  title: string
  description: string
  action?: ReactNode
  children?: ReactNode
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

/**
 * A list already narrowed to one parent record.
 *
 * No filter box and no pager: the rows are a handful a reader takes in at once,
 * so both controls offer to narrow something that is not wide. `pageSize` still
 * caps what is drawn — see hidePager on RecordListView.
 */
function EmbeddedList(props: {
  module: string
  basePath: string
  filter: Record<string, string>
  hiddenColumns?: string[]
  renderCell?: React.ComponentProps<typeof RecordListView>['renderCell']
  emptyMessage: string
}) {
  return (
    <RecordListView
      module={props.module}
      collection={props.module}
      basePath={props.basePath}
      filter={props.filter}
      hiddenColumns={props.hiddenColumns}
      renderCell={props.renderCell}
      pageSize={10}
      hideSearch
      hidePager
      emptyMessage={props.emptyMessage}
    />
  )
}

function ContactPanel({
  role,
  accountId,
  account,
  unsetMessage,
}: {
  role: string
  accountId: string | undefined
  /** The resolved account record, for its name. Absent while it loads. */
  account: Values | undefined
  unsetMessage: string
}) {
  const navigate = useNavigate()

  return (
    <RelatedSection
      title={role}
      description={
        accountId
          ? account
            ? `Contacts at ${displayNameOf(account)}.`
            : 'Loading the account…'
          : unsetMessage
      }
      action={
        accountId && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/contacts/new?account=${accountId}`)}
          >
            <PlusIcon className="size-4" />
            Add contact
          </Button>
        )
      }
    >
      {accountId && (
        <EmbeddedList
          module="contacts"
          basePath="/contacts"
          filter={{ account: accountId }}
          hiddenColumns={['account']}
          renderCell={contactListCell}
          emptyMessage="No contacts at this account yet."
        />
      )}
    </RelatedSection>
  )
}
