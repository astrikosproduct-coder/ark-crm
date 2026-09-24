# Metadata model v2 — Step 1 sign-off list

**Status:** approved 24 Sep 2026 · **Prepared:** 24 Sep 2026 · **Source:** development database, read-only

**The rule for all of it: the structure changes, the behaviour doesn't.** Every
outcome below keeps what a user sees and what a save does exactly as today.
A behaviour change is not made here, even where one looks tempting; it is
listed under G as a question for later.

**Production check.** This list was read from development. Before Step 3 runs on
production, the same inventory is re-run there. Production publishes live, so
its register may differ. Any row not listed here stops the script for a decision.

---

## A. The 55 shared pipeline fields

Today 184 definitions sit in one shared `pipeline` scope used by Leads,
Opportunities and Deals. 129 of them are on one module only and simply move to
that module. The other **55 are shared**, and each gets one of three outcomes.

After v2: about **234 definitions**, each owned by exactly one module.
Every `api_name` keeps its name. No business column or value changes.

### A1. Shown live on Opportunities and Deals → "From the Lead" items (26)

The Lead keeps the one definition. The Opportunity and Deal layouts **point at
the Lead's field**. They own nothing, the value is shown live, and it can't be edited there
(decision of 24 Sep: keep read-through live).

| Field | Lead section | Lead requirement |
|---|---|---|
| Opportunity Name | Stage 0 — Connect | Mandatory |
| BD Owner | Stage 0 | Mandatory |
| Deal Source | Stage 0 | Mandatory |
| Opportunity Type | Stage 0 | Mandatory |
| S!aP Solution Suite | Stage 0 | Mandatory |
| Segment | Stage 0 | Mandatory |
| Theme | Stage 0 | Mandatory |
| Currency | Stage 0 | Mandatory |
| FX Rate (local per 1 USD) | Stage 0 | Conditional |
| Partner Deal Registration | Stage 0 | Conditional |
| Booking Region | Stage 0 | Optional |
| Destination Region | Stage 0 | Optional |
| Country | Stage 0 | Optional |
| City / State | Stage 0 | Optional |
| Primary Contact | Stage 0 | Optional |
| Gorilla Flag | Stage 0 | Optional |
| Lighthouse Project | Stage 0 | Optional |
| **End Client** *(G1, decided: live on the Deal too)* | Stage 0 | Mandatory |
| Suite Demonstrated | Stage 1 — Demo Presentation | Mandatory |
| Alliance Structure | Stage 3 — Prescription | Mandatory |
| Consultant / Specifier | Stage 3 | Mandatory |
| Pre-Bid Alliance Partner | Stage 3 | Mandatory |
| Probable Award Date | Stage 3 | Mandatory |
| Presales Owner | Stage 3 | Optional |
| Sales Owner | Stage 3 | Optional |
| Total Project Value | Stage 3 | Optional |

### A2. Copied once into the Deal → Deal owns the field + a Conversion Mapping row (6)

| Field | Owned by, before the Deal | Deal gets its own field, filled by mapping from |
|---|---|---|
| ARR (Annual Recurring) | Opportunity (Stage 4) | Opportunity → Deal |
| Contract Years | Opportunity (Stage 4) | Opportunity → Deal |
| One-Time Revenue | Opportunity (Stage 4) | Opportunity → Deal |
| 3rd-Party Revenue — One-Time | Opportunity (Stage 4) | Opportunity → Deal |
| 3rd-Party Revenue — Recurring (per year) | Opportunity (Stage 4) | Opportunity → Deal |
| Customer (Partner / SI) | Lead (Stage 0; the Opportunity shows it live) | Lead, through the Opportunity → Deal — *G1: stays the Deal's own field* |

On the Deal these sit in **Stage 7 — Commercial Terms**, Mandatory, as today.

### A3. Own value on each module → split, one definition per module (23)

Decision of 24 Sep: split system fields as well, as Zoho does. Each module can then rename,
reorder or change its copy on its own.

| Field | On | Labels after the split |
|---|---|---|
| Lead Status | L · O · D | **Lead Status · Opportunity Status · Deal Status** (today's overrides become real labels) |
| Lead Stage | L · O | **Lead Stage · Opportunity Stage** |
| Expected Close Month | L · O · D | Deal keeps **"Expected Close Month (at conversion)"**; Lead Mandatory, Opportunity Mandatory from Stage 0, Deal Optional — unchanged |
| Incremental Value | L · D | Lead: Stage 0, Conditional · Deal: Stage 9, Mandatory — unchanged |
| Parent Lead | O · D | Opportunity: System · Deal: Mandatory — unchanged |
| Probability (%) · Progression % | L · O · D | unchanged |
| Overall RAG · Next Milestone · Next Milestone Date | L · O · D | unchanged |
| Closed Lost Reason Code · On Hold Reason · Override Justification | L · O · D | unchanged |
| Stage Skip Reason · Stage Reversal Reason | L · O · D | unchanged |
| Days in Current Stage · Days Since Last Update | L · O · D | unchanged (computed) |
| Is Primary Pursuit · Pursuit Group | L · O · D | unchanged (system) |
| Created By · Created Date · Modified By · Modified Date | L · O · D | unchanged (system) |

---

## B. Conversion Mapping: the first rows

Written from today's behaviour, nothing added. **Editable** rows can be changed in
Setup once the editing screen exists (item 3). **Locked** rows are shown greyed.

| Path | Source → Target | Row |
|---|---|---|
| **Opportunity → Deal** | ARR · Contract Years · One-Time Revenue · 3rd-Party One-Time · 3rd-Party Recurring → same fields on the Deal | Editable |
| | Customer (Partner / SI) → Deal's own field | Editable — *G1: stays the Deal's own field* |
| | Parent link · Stage · Status · Progression / Probability | Locked (system) |
| **Lead → Opportunity** | Nothing is copied: the Opportunity shows the Lead's fields live (A1) | — |
| | Parent link · Stage · Status · Progression / Probability | Locked (system) |
| **Lead → Deal (paid pilot)** | Pilot Fee → Contract Value | Locked — *see G2* |
| | Pilot PO Received Date → PO Received Date | Locked |
| | Opportunity Name → Deal Name (+ " — Paid POC") | Locked |
| | Customer (Partner / SI) → Deal's own field | Locked — End Client is shown live, not copied |

The paid-pilot copies are hard-coded in `backend/app/progression.py` today. v2 turns them into
rows that show what happens, so they are no longer hidden.

**To verify in Step 2:** where the Deal's *"Expected Close Month (at conversion)"* gets
its value when the Deal is created (the convert dialog or the server). Whichever it is
becomes an Opportunity → Deal mapping row.

---

## C. Partners → parent of three child modules

**Nothing is deleted.** The Partners screen, the `partners` module and every record stay.
The `deal_registrations` and `registration_conflicts` tables are not touched.
Only the register rows that *describe* their fields move.

```
Partners                      stays — the parent; the Partners screen is unchanged
 ├─ Deal Registrations        new module — 18 fields, own layout
 │    └─ Conflicts            new module — 13 fields, own layout
 └─ Partner Scorecards        new module — 8 fields, HIDDEN until built
```

| Moves to | Fields |
|---|---|
| **Deal Registrations** | Registration ID · Partner · End Client · Project Name · **Currency** · Estimated Value · Expected Timeline · Partner Role · Submitted Date · Acknowledged Date · Acknowledgement SLA Met · Exclusivity Start Date · Exclusivity Expiry Date · Registration Status · Withdrawn Date · Withdrawal Reason · Extension Reason · Linked Lead |
| **Conflicts** | Conflict ID · Registration A · Registration B · Who Registered First · Stronger Client Relationship · Better Delivery Capability · Decision · Primary Registration · Decision Rationale & Evidence · Evidence Link · Decision Date · Decided By · Both Partners Notified |
| **Partner Scorecards** (hidden) | Scorecard ID · Partner · Quarter · Leads Registered · Conversion Rate to Stage 4+ · Revenue Closed · Partner Satisfaction Score · QBR Date |

- **Currency on a registration** borrows the *Lead's* Currency definition today. It becomes
  the registration's own field, on the global Currency list (D).
- **Data:** development holds 0 registrations and 0 conflicts, with nothing in their
  `custom_fields`. Production is counted in the production check, and nothing there moves either.
- **Partner Attributes** (4 fields) stay on Accounts behind their visibility rule
  (decision of 24 Sep: no record types yet).
- The hand-written remap in `frontend/src/lib/spec/index.ts` (`registrations → partners`,
  `conflicts → partners`) is deleted in Step 4.

---

## D. Picklists: 7 global, 7 local (decided 24 Sep, G3/G4)

| Picklist (key unchanged) | Label today → after | Used by after v2 | Outcome |
|---|---|---|---|
| `leads__currency` | Leads — Currency → **Currency** | Leads · Deal Registrations | **Global** |
| `leads_stage` | Leads Stage → **Pipeline Stage** | Lead Stage · Opportunity Stage | **Global** (values follow the Stages table) |
| `closed_lost_reason_code` | → **Closed Lost Reason** | Leads · Opportunities · Deals | **Global** |
| `overall_rag` | Overall Rag → **Overall RAG** | Leads · Opportunities · Deals | **Global** |
| `region` | Region | Accounts · Leads (Booking and Destination Region) | **Global** |
| `segment` | Segment | Accounts · Leads | **Global** |
| `contacts__dial_code` | → **Dial Code** | Contacts (Phone and Mobile) | **Global** — *found on the dry run: two fields share it* |
| `leads__lead_status` | → **Lead Status** | Leads only | **Local** (G3) |
| *new* `opportunities__lead_status` | **Opportunity Status** | Opportunities only | **Local** (G3) — starts as a copy of today's values minus POC/Pilot Deal |
| *new* `deals__lead_status` | **Deal Status** | Deals only | **Local** (G3) — starts as a copy of today's values; the only list holding POC/Pilot Deal |
| `leads__alliance_structure` | → **Alliance Structure** | Leads only | Local |
| `leads__deal_source` | → **Deal Source** | Leads only | Local |
| `leads__opportunity_type` | → **Opportunity Type** | Leads only | Local |
| `theme` | Theme | Leads only | Local |

**Status lists after G3:**
- **The `extensions.json` rule that hides POC/Pilot Deal on Leads and Opportunities is deleted.**
  The value is simply not on those lists.
- **Stored values stay the same.** Each new list copies today's value keys exactly, so every
  saved status still matches and nothing is rewritten.
- **System values are protected.** The code reads the keys for Open, On Hold, Closed Lost,
  Converted and POC/Pilot Deal: revenue totals, the Kanban, the stage-move rules. Their labels can
  be renamed, but they can't be removed or deactivated. The server refuses with a clear message.
  Any other value can be added, renamed or retired freely per module.

Keys never change, because every stored value is written under them. Only labels change.
The other 102 picklists are already used by one module and become local.

## E. Modules hidden, not deleted

Hidden means: not shown in Setup's module list, not in the spec the app reads, and every
row kept. Nothing is dropped.

| Module | Why hidden | Placements kept |
|---|---|---|
| `administration` | Users and Roles are hand-built screens; nothing reads these rows | 100 |
| `demo_module` | Leftover, empty | 0 |
| `bids_pocs` · `quotes` · `products` · `activities_docs` | Not built yet; each is un-hidden when its phase starts | 85 · 68 · 50 · 21 |
| `partner_scorecards` (new, C) | Not built yet | 8 |

---

## F. Tidy-ups that ride along

- The Opportunity / Deal section **"READ THROUGH THE PARENT — resolved from the parent, never
  stored here"** is renamed **"From the Lead"**. The old label breaks the copy rule
  (no system words).
- Picklist labels lose their module prefix (D).
- `field_metadata` (568 rows) is retired in Step 6. Nothing in this list depends on it.

---

## G. Judgement calls

| # | Question | Decision |
|---|---|---|
| **G1** | End Client and Customer (Partner / SI) on the Deal | **Show the Lead's value live** (24 Sep). End Client: done, see A1. Customer (Partner / SI) **stays the Deal's own field** (confirmed 24 Sep) |
| **G2** | Paid-pilot mapping rows | **Locked** (24 Sep): shown in Setup, copy happens exactly as today, nobody can change or remove the row |
| **G3** | Status picklists | **Local, one list per module** (24 Sep): see D |
| **G4** | Global / local split | Settled by G3: 7 global, 7 local (Dial Code added on the dry run) |

**G1 consequence, for confirmation.** A converted record is read-only, so a field shown live
from the Lead can no longer be changed anywhere once the Lead converts at Stage 3.
- **End Client:** fine. The Opportunity already can't change it today, and it must not drift.
- **Customer (Partner / SI):** today the Deal can change it at Stage 7, where it is Mandatory,
  because the partner who signs the contract is not always the one expected at Stage 0.
  Live would take that away.

**Recommended:** End Client live · Customer (Partner / SI) stays the Deal's own field, copied
at conversion (as today).

**What G1 changes in the server:** the places that read the Deal's own End Client column switch
to the Lead's value, through the Deal's Parent Lead, which every Deal has. Those places are the
duplicate-pursuit check, the Pursuit Group End Client guard, the refusal to delete an Account a
pursuit names, global search and Lead deletion. The Deal column stays and keeps its values, but
nothing writes it or shows it from then on (never a DROP COLUMN).

**Approved:** A–F, with the changes above.
