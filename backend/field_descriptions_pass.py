"""
The field-description pass for the six live modules.

    python field_descriptions_pass.py            # show what would change
    python field_descriptions_pass.py --write    # write it, then publish

WHY THIS IS A SCRIPT AND NOT SIXTY CLICKS

The descriptions live in `field_definitions`, are edited in Administration and
reach the frontend only by publishing (CLAUDE.md: PostgreSQL -> generated JSON,
never the other way). Sixty-two of them needed rewriting in one consistent
voice, which is a job for one reviewable diff rather than sixty dialogs, and a
script is the only form of it anyone can read back later.

WHAT WAS WRONG WITH THE OLD ONES

Nothing was blank. Every one of the 356 fields across Leads, Opportunities,
Deals, Accounts, Contacts and Partners already had a description, and about a
quarter of them restated the label and taught nothing:

    full_name        "The person's full name."
    mobile           "Mobile number."
    demo_completed   "Confirms Demo is completed"

That last one is the tell. It says what the checkbox is CALLED, not what has to
be true before someone ticks it -- which is the only thing a reader opening the
tooltip wanted to know.

THE HOUSE STYLE

Four sentences at most, in this order, and only the ones that earn their place:

    WHAT IT IS        One sentence, never a restatement of the label.
    WHEN TO FILL IT   The stage or the trigger.
    WHAT COUNTS       Inclusions and exclusions, where they are arguable.
    WHERE IT LANDS    What downstream reads it, where something does.

Under 255 characters, enforced by migration 0033 and by
app/schemas_metadata.py::DESCRIPTION_MAX_LENGTH. The cap is a layout contract:
the same sentence is read in the field tooltip, row 4 of the Excel import
template and the export workbook, and a tooltip that scrolls has stopped being
one.

A DEFINITION IS SHARED, SO WRITING IT ONCE FIXES EVERY MODULE

Keyed by definition id, not by module: `one_time_revenue` is one row placed on
both Opportunities and Deals, and it should read the same on both.

WHAT THIS DELIBERATELY DOES NOT TOUCH

- partners.exclusivity_expiry_date's computed_formula, which reads "Start date
  plus 90 days" and is wrong by one day: the window INCLUDES the start day, so
  it is 89. That contradiction is a deliberate, flagged finding (see
  spec/extensions.json $exclusivity_days_note and open_questions) and silently
  correcting it here would delete the finding. The description says how the date
  is derived without restating the disputed number.
- The three partner scorecard metrics (leads_registered,
  conversion_rate_to_stage_4+, revenue_closed). Partner scorecards are out of
  scope (CLAUDE.md), nothing computes them, and inventing a formula for an
  unbuilt feature would put a rule in the register that no one agreed.
"""

from __future__ import annotations

import sys

# The register is full of em dashes and these sentences carry minus signs, so a
# report line cannot be printed on a cp1252 console without this. A script that
# crashes while describing its own diff is worse than no script.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.database import SessionLocal
from app.models import FieldDefinition
from app.schemas_metadata import DESCRIPTION_MAX_LENGTH

# --------------------------------------------------------------------------
# Descriptions, by definition id. The id is in the comment beside each so a
# reviewer can find the row; the api_name is asserted before anything is written.
# --------------------------------------------------------------------------

DESCRIPTIONS: dict[int, tuple[str, str]] = {
    # ---- Accounts
    593: ("phone", "The organisation's main switchboard. A named person's own line belongs on their Contact record; this is the number to try when you have no name."),
    595: ("segment", "The market this client operates in. Drives the segment view on the dashboard, so pick the market the PROJECT serves rather than the parent group's main business."),
    596: ("website", "The organisation's own corporate site, used to confirm you have the right legal entity when two clients share a name. Not a project microsite or a social profile."),

    # ---- Contacts
    803: ("account", "The organisation this person works for. Contacts are external people at a client or partner; an Astrikos colleague is a User and never a Contact."),
    807: ("email", "Their work address, which is what tells two people with the same name apart. A personal address is not recorded here."),
    808: ("engagement_owner", "The Astrikos employee who owns this relationship and is expected to know what has changed. A User, not a Contact."),
    810: ("full_name", "The person's name as they use it professionally — as it appears in their email signature or on a tender document. Used to find them and to name them on a POC brief."),
    812: ("job_title", "Their title at the organisation, as they give it. A title is not authority: what they can actually decide belongs in Contact Role."),
    813: ("linkedin", "Their professional profile, for checking a role or a move before a meeting. Most useful when a contact has gone quiet."),
    814: ("mobile", "The number that reaches them directly. Leave it blank rather than guessing; the dial code belongs with the number."),
    815: ("notes", "What you would tell a colleague taking this relationship over tomorrow: what they care about, who they listen to, what went wrong last time. Not a meeting log."),
    816: ("phone", "Their desk or switchboard number. If all you have is a mobile, put it in Mobile rather than here."),

    # ---- Deals
    867: ("booking_date", "The day the order was booked internally. It is NOT the day the deal was won: Won is the day the PO is received, and no field records that yet, so never stand this in for it."),
    885: ("contract_expiry_date", "The last day of the current contract term, which is what the renewal conversation runs to. Not the warranty end and not the go-live anniversary."),
    889: ("contract_signed_date", "The day both parties executed the contract. The signature date itself, not the day it was sent out or came back to us."),
    898: ("csat_date", "The day the satisfaction score beside this was measured. A score with no date cannot be read as current, so fill both or neither."),
    936: ("guarantee_—_issue_date", "The day the bank issued the instrument. Expiry runs from here, so take it from the guarantee itself rather than from the day we asked for it."),
    937: ("guarantee_—_issuing_bank", "The bank that issued the instrument, named as it appears on it. Needed to chase a release, which the client's own bank cannot do for us."),
    941: ("guarantee_—_value", "Face value of the bank guarantee, in the deal currency. A guarantee above 10% of contract value, or running past 12 months, breaches a commercial threshold and needs approval."),
    949: ("kickoff_meeting_date", "The day delivery formally starts with the client in the room, planned or held. If it moves, move this — handover is chased from it."),
    1007: ("renewal_signed_date", "The day the renewal was executed. It stays blank while a renewal is still being negotiated, however likely it looks."),
    1008: ("renewal_status", "Where the renewal conversation has actually reached. A contract close to expiry with nothing recorded here reads as unworked."),
    1036: ("warranty_end_date", "The last day defects are put right at no charge. Separate from contract expiry: warranty usually ends first, and support after it is chargeable."),

    # ---- Shared by Leads, Opportunities and Deals
    868: ("booking_region", "The Astrikos region the revenue is booked into, which decides whose numbers it lands in. Often not where the work happens — a Dubai-booked project can be delivered in Riyadh. See Destination Region."),
    872: ("city_state", "The city or state the project is actually in, within the country above. Where the work happens, not where the client's head office sits."),
    877: ("closed_lost_reason_code", "Why this pursuit was lost, from the fixed list, so that losses can be counted and compared. Recorded at the stage it was lost and never borrowed from an earlier one."),
    895: ("created_by", "Who created the record. Stamped from the signed-in user and never editable, which is what makes it worth relying on."),
    897: ("created_date", "When the record was created. Stamped by the system and shown on the company clock."),
    906: ("days_in_current_stage", "Days since the record entered the stage it is in now, counted from the recorded move — so a record that went back starts again. Past 90 days it appears on the dashboard's at-risk list."),
    961: ("modified_by", "Who last changed the record. Stamped from the signed-in user; History shows which fields they changed."),
    963: ("modified_date", "When the record last changed. Stamped by the system. More than 30 days without a change counts as stale on the dashboard."),
    965: ("next_milestone_date", "When the milestone named beside this is due. Feeds the dashboard's due list, so a date in the past shows as overdue until the milestone itself is moved on."),
    1019: ("stage_reversal_reason", "Why this record moved back to an earlier stage. Required on every backward move and kept on the record; a reversal without one cannot be saved."),
    1023: ("suite_demonstrated", "Which S!aP suite was actually shown in the demo — not what was offered, quoted or planned. Blank until the demo has happened."),

    # ---- Leads
    857: ("agreed_next_step", "What both sides agreed would happen next, taken from what the client said rather than what we hoped. Blank means nothing was agreed, which is itself worth knowing."),
    900: ("ctb_approval_date", "The day the Commit to Bid decision was taken, whatever it was. Approved, deferred and no-bid all have a date."),
    916: ("demo_completed", "Tick once the demo has actually been delivered to the client. A demo that was scheduled, rescheduled or no-showed does not count."),
    983: ("pilot_commercial_model", "Whether the client pays for the pilot. Marking it paid opens a POC/Pilot Deal at Close for the pilot fee and converts this Lead, so set it only once payment is agreed."),

    # ---- Opportunities
    854: ("agreed_credit_period_days", "Days from invoice to payment as agreed with the client. Beyond 60 days breaches a commercial threshold and needs approval before the deal can close."),
    855: ("agreed_ld_cap_pct", "The liquidated damages cap accepted in the contract, as a percentage of contract value. Above 10% breaches a red line that only CEO and Legal can clear."),
    865: ("bid_submission_date", "The day the bid was actually submitted. Compared against the deadline to say whether we were on time, so record the real date even when it is late."),
    875: ("client_tender_reference", "The client's own RFP or tender number, exactly as they wrote it. It is the reference they will quote back at us, so copy it rather than tidy it."),
    886: ("contract_review_sign_off_by", "Who signed off the contract review, and so who is accountable for the terms. On a one-person approval chain this is the submitter, which is recorded openly rather than hidden."),
    955: ("loi_received_date", "The day the letter of intent arrived from the client. An LOI is intent, not a contract — the signature date is recorded on the Deal."),
    958: ("milestone_—_invoice_date", "The day this milestone was actually invoiced. Blank until the invoice is raised, however clearly it is due."),
    959: ("milestone_—_payment_received_date", "The day the money for this milestone arrived. Blank until it has cleared: a promised payment is not a received one."),
    1011: ("rfp_received_date", "The day the formal RFP or tender document reached us. The bid clock starts here, so take it from the document rather than from a conversation about it."),
    1025: ("technical_approval_date", "The day technical approval came through from the client. Blank while evaluation continues, whatever the informal signals say."),

    # ---- Partners
    818: ("acknowledged_date", "The day Astrikos acknowledged the registration back to the partner. The clock runs from submission, so a late date records a missed service level rather than tidying one away."),
    824: ("decided_by", "The Astrikos person who adjudicated between the competing registrations, and so who is accountable for the outcome."),
    825: ("decision", "Which registration prevailed. It settles exclusivity for the project, so the partner who lost is told rather than left waiting."),
    826: ("decision_date", "The day the adjudication was decided. Exclusivity still runs from the winning registration's own start date, not from this one."),
    827: ("end_client", "The organisation the opportunity is with — the End Client, never the partner registering it. Two partners naming the same End Client and project is what raises a conflict."),
    828: ("estimated_value", "The partner's own estimate of the deal value, in the currency they gave it in. Their number, not ours: our estimate lives on the Lead."),
    829: ("exclusivity_expiry_date", "The last day this registration holds exclusivity. Worked out from the start date, with the window counted inclusive of that day. Move the start date rather than editing this."),
    830: ("exclusivity_start_date", "The day the exclusivity window opens. Expiry is counted from here, so this is the date to change if the window moves."),
    837: ("project_name", "The specific project being registered, named closely enough to tell it apart from another project at the same client. Vague names are what make two registrations look like one."),
    839: ("quarter", "The quarter this scorecard covers. Scorecards are read side by side across quarters, so a mis-set quarter hides the trend rather than showing it."),
    840: ("registration_a", "The first of the two competing registrations being adjudicated."),
    841: ("registration_b", "The second of the two competing registrations being adjudicated."),
    849: ("partner", "The partner organisation this scorecard covers. An Account carrying a partner type — there is no separate partner record anywhere."),
    850: ("partner", "The partner organisation this scorecard covers. An Account carrying a partner type — there is no separate partner record anywhere."),
}

# --------------------------------------------------------------------------
# Formulas for computed fields that had none. Prose, for the reader: the
# executable form is computed_expr, and these two are resolved by named
# functions rather than an expression (see src/lib/spec/resolvers.ts), which is
# exactly why nobody could see how they worked.
# --------------------------------------------------------------------------

FORMULAS: dict[int, tuple[str, str]] = {
    906: ("days_in_current_stage", "Today − the date the record entered its current stage"),
    907: ("days_since_last_update", "Today − Modified Date"),
}


def main() -> int:
    write = "--write" in sys.argv
    changed = skipped = 0

    with SessionLocal() as db:
        definitions = {d.id: d for d in db.scalars(select(FieldDefinition))}

        for definition_id, (api_name, text) in DESCRIPTIONS.items():
            definition = definitions.get(definition_id)
            if definition is None:
                print(f"  MISSING  {definition_id} ({api_name}) — no such definition")
                skipped += 1
                continue
            # The id is the key, so an api_name that has drifted means the row
            # is not the one this text was written for. Refuse rather than
            # write a description onto the wrong field.
            if definition.api_name != api_name:
                print(f"  MISMATCH {definition_id}: expected {api_name}, found {definition.api_name}")
                skipped += 1
                continue
            if len(text) > DESCRIPTION_MAX_LENGTH:
                print(f"  TOO LONG {definition_id} ({api_name}): {len(text)} > {DESCRIPTION_MAX_LENGTH}")
                skipped += 1
                continue
            if definition.description == text:
                continue
            print(f"  {api_name}")
            print(f"    was: {definition.description}")
            print(f"    now: {text}")
            if write:
                definition.description = text
            changed += 1

        for definition_id, (api_name, formula) in FORMULAS.items():
            definition = definitions.get(definition_id)
            if definition is None or definition.api_name != api_name:
                print(f"  SKIP formula {definition_id} ({api_name}) — not found or renamed")
                skipped += 1
                continue
            if (definition.computed_formula or "") == formula:
                continue
            print(f"  {api_name} formula: {formula}")
            if write:
                definition.computed_formula = formula
            changed += 1

        if write:
            db.commit()

    print()
    print(f"{changed} change(s){' written' if write else ' — dry run, pass --write'}, {skipped} skipped")
    if write:
        print("Now publish from Administration (or regenerate) so spec/fields.json picks these up.")
    return 1 if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
