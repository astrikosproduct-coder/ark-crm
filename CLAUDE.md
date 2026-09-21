# ARK CRM — clickable prototype

> Copy this file to the root of the prototype repo as `CLAUDE.md`.
> Claude Code loads it automatically at the start of every session.

## What this repo is

A **clickable prototype** of ARK CRM, an in-house CRM for **Astrikos** — a MEA platform
company selling the **S!aP** suite into smart cities, datacentres, utilities, O&G and
industrial clients.

Its purpose is to find gaps in the field list and the business rules **before** the real
product is built. It is shown to BD and management as if it were a real product.

**It is not the real product.** There is no workflow automation — do not add it. It is
*mostly* browser-only: Round 1 moved users, accounts and contacts onto a real FastAPI +
PostgreSQL backend, and every other module is still MSW over `localStorage`. See hard
rule 1 for exactly which is which.

**Authentication IS real, as of Phase 1.** This file said "there is no authentication —
do not add it" until Sep 2026, which is now wrong and was actively misleading: sign-in is
Microsoft Entra, the session is a server-signed cookie, and `app/auth.py::current_user` is
the single place identity is decided. Every data router is mounted with
`dependencies=PROTECTED` (`require_access`) and Administration with `ADMIN_ONLY` — see
`app/main.py`. A signed-in user with no roles is a real, expected state and gets nothing
until an administrator grants one.

So **identity is available server-side on every request, and must be taken from there.**
Never accept `created_by`, `modified_by`, an audit `actor`, or a transition `actor`/
`timestamp` from a request body — see `SYSTEM_STAMPED` in `app/routers/leads.py` and the
docstring on `app/audit.py::record_audit`. What is still out of scope is role-based
*permissions* beyond "has any role" / "is admin".

## Hard rules — do not break these

1. **Browser-only, except the modules migrated to PostgreSQL.** Never add Express, Next
   API routes or Prisma. Most modules' data lives in the browser, but these are real,
   persistent data behind FastAPI + SQLAlchemy + PostgreSQL in `backend/`:
   | Migrated (Round 1) | Tables | Served at |
   |---|---|---|
   | Users, roles | `users`, `roles`, `user_roles` | `/api/admin/*`, `/api/users` |
   | Accounts (incl. Partners) | `accounts`, `account_types` | `/api/accounts` |
   | Contacts | `contacts` | `/api/contacts` |

   | Migrated (Phase 1) | Tables | Served at |
   |---|---|---|
   | Leads | `leads`, `lead_demo_attendees`, `lead_feature_gaps` | `/api/leads` |
   | Opportunities | `opportunities`, `opportunity_payment_milestones` | `/api/opportunities` |
   | Deals | `deals`, `deal_bid_commitments`, `deal_expansion_use_cases` | `/api/deals` |

   Phase 1 completes the six committed modules — Leads, Opportunities, Deals,
   Accounts, Contacts and Partners are all real, persistent PostgreSQL data now.
   Only `leads` carried seed data across (`migrate_leads.py`, 3 of 6 seed rows —
   two sit past the Leads stage range and one names a missing Account);
   Opportunities and Deals start empty and fill from real pipeline use.

   | Migrated (Round 6) | Tables | Served at |
   |---|---|---|
   | The field register itself | `modules`, `sections`, `field_metadata`, `picklists`, `picklist_values`, `stages`, `metadata_versions` | `/api/admin/metadata/*` |
   | Dynamic admin-field values **and per-stage values** | `custom_fields` JSONB on accounts, contacts, leads, opportunities, deals | the module's own endpoint |

   | Added (17 Sep 2026) | Tables | Served at |
   |---|---|---|
   | User feedback | `feedback` (+ picklists `feedback__category`, `feedback__status`) | `/api/feedback` — anyone sends; **DEVELOPER-only** to read, enforced by `app/auth.py::require_developer` |
   | Excel / CSV import & export | no table — files are read and discarded | `/api/spreadsheets/{module}/…` — see below |

   **Import / export** (`backend/app/spreadsheets/`). Export: every live module, a workbook of
   Summary + one sheet per form section + Stage history + child lists, rows from the module's
   own list endpoint under the screen's filters. Import: Leads, Accounts, Contacts, Partners —
   **never Opportunities or Deals** (born by conversion), and **Leads at Stage 0 only** (a Stage 1
   move has blocking checks a sheet cannot confirm). Every row goes through the module's own
   create logic (`leads.insert_lead`, `create_account`, `create_contact`) inside one outer
   transaction with a savepoint per row: preview rolls back, commit is all-or-nothing. Rows
   are checked like a form SAVE — formats, choices, lookups — not Mandatory fields.
   **The sample file** (`workbook.template_workbook`): row 1 Astrikos band · row 2 form sections ·
   row 3 labels · row 4 what to enter · row 5 "Only if …" from the visibility condition · data
   from row 6. The importer finds the label row by matching labels and skips rows 4–5 by their
   exact text, so a plain row-1-header file still works. A multiselect with ≤6 choices is one
   Yes/No column per choice ("Account Type · End Client"); lookups are dropdowns of live names
   on a hidden Lists sheet. **Never guess a value:** an unrecognised choice is answered once on
   the review screen (`answers`), missing lookup names are grouped per column, an ambiguous
   date like 03/04/2026 is refused. A value in a column whose visibility condition is false for
   that row is **left out with a warning**, not refused (decided 17 Sep 2026) — and only when
   every field the rule reads is on the sheet. No undo of an import (declined 17 Sep 2026).
   **Pipeline lists** share `app/list_query.py` (equality, `_ne`, `_gte/_lte/_gt/_lt`, text
   `_is/_isnt/_contains/_ncontains/_starts`, `_empty=1|0`, one dot into `revenue.usd`,
   number-aware sort) — and so do Accounts, Contacts and Registrations. Every live list has a
   Zoho-style Filter panel (`components/list/ListFilterBar.tsx`, state in the URL via
   `lib/listFilters.ts`): Filter button first, then the record search box OUTSIDE the panel;
   inside, a find-a-field box, "Common filters" (the list view's `filters`, ending with the
   module's commercial figure) and "Filter by fields" (the module's OWN fields only — never
   read-through identity unless pinned as common). Shared by List and Kanban. No sort panel
   (removed 17 Sep 2026 at the user's request); column headers still sort. Opportunity/Deal list rows carry their
   read-through identity (`app/read_through_rows.py`) — list rows only, never a record read.

   Round 1 is complete. Do not delete them, and do not migrate another module without
   being asked.
   **Round 6 stores metadata, not business data.** Those seven tables define what a record
   may contain; they never hold a lead, an account or a quote. Deleting a field there is a
   logical delete — `field_metadata.status = 'deleted'` — and **never** a `DROP COLUMN`:
   the business column and every value in it survive, which is what makes restore real.
   Administration must never issue schema DDL against a business table.
   **Two storage modes, and `field_metadata.storage` says which.** A register field has a
   typed column and keeps it (`storage='column'`). A field created in Administration has no
   column and is never getting one — its values live in that table's `custom_fields` JSONB,
   keyed by api_name (`storage='custom_fields'`). Never infer the mode from `origin` or from
   a key looking unfamiliar; read the column. An unknown key is not data and is not stored.
   **`custom_fields` also holds per-stage values** — `<api_name>__s<stage>`, as in
   `on_hold_reason__s3` or `expected_close_month__s1`. A reason is captured at the stage it
   was given and must not carry forward: a lead put on hold at Stage 1 and again at
   Stage 3 has two different answers, and one column per record cannot hold both.
   Twenty columns per field is not a schema, so they live in the same JSONB, admitted
   by the same rule as everything else: **only if the BASE name is an active placement
   on that module.** `on_hold_reason__s3` is storable because `on_hold_reason` is a
   field there; `rfp_documnet__s3` and `on_hold_reason__sx` are still refused. Before
   10 Sep 2026 `resolve_write` dropped these keys silently — they are not columns and
   not Administration-created fields — so from the moment Leads, Opportunities and
   Deals moved to PostgreSQL, no per-stage value ever persisted. See
   `app/custom_fields.py` and `src/lib/stageScope.ts`.
   **`opportunities` is a real module row** (Round-6 gap closure), even though the register
   has no such sheet. `modules.is_pipeline` / `stage_field` / `parent_module` / `parent_link`
   and `stages.owner_module` hold the pipeline structure, and `spec/module_split.json`'s
   structural blocks are generated from them. Opportunity FIELD rows are deliberately not
   materialised — they are projections of Leads rows, and storing them would duplicate the
   register. See `app/module_split.py`.
   **Their seed files were removed** — `spec/seed/users.json`, `accounts.json` and
   `contacts.json` no longer exist; PostgreSQL is the source of truth. Everything else
   still seeds from `spec/seed/*.json`.
   **Users are internal ARK employees; Contacts are external people at an Account.**
   Never mix them: an `engagement_owner` is a user, a `primary_contact` is a contact.
   **Partners is a view over `accounts`**, not a table. An account is a Partner when its
   `account_type` includes a partner type. Never create a partners table.
2. **All data access goes through the Axios client in `src/lib/api.ts`.** Components call
   `/api/...` exactly as they will in production. MSW intercepts and answers from the store.
   This is what makes the prototype reusable as the Phase 1 frontend — never bypass it by
   reading the store directly from a component, and never add a second Axios instance.
   **These paths pass through to FastAPI** — `/api/admin/*`, `/api/users`,
   `/api/accounts` and `/api/contacts` (each with its `/*` form). Round 6's
   `/api/admin/metadata/*` needed no new entry anywhere: the `/api/admin/*` wildcard already
   matches it in both places, which is exactly why it was mounted under that prefix.
   Their handlers at the top of
   `src/mocks/handlers.ts` must stay FIRST, or the catch-alls below will swallow them.
   Each also needs an entry in `vite.config.ts`'s `server.proxy`, or the passthrough lands
   on Vite's HTML fallback. **Both, or it silently returns HTML.**
   `/api/feedback` and `/api/spreadsheets/*` pass through as well (17 Sep 2026).
   `/api/dashboard` passes through too: it is read-only aggregates over the live pipeline
   (`backend/app/routers/dashboard.py`), computed with `app/revenue.py`'s rule so its
   totals reconcile with the boards. It reads only PostgreSQL modules. Gates, Quotes and
   POCs stay off it until they migrate.
   Every other `/api/*` collection is still answered by MSW from the store.
   A migrated collection must also be listed in `src/mocks/userDirectory.ts`, so MSW can
   still join its display names onto other modules' list rows.
3. **Never hardcode a field.** Every form renders from `spec/fields.json`. If a field is
   missing from a screen, the fix is in the spec, not in a component.
   *Two documented exceptions, both in Administration:*
   - `src/components/admin/UserDialog.tsx` is hand-built. The register models Roles as a
     `multiselect` picklist, but the real thing is a junction-table relation (`user_roles`)
     saved through its own endpoint, which the form engine has no vocabulary for. The engine
     is deliberately left unchanged; see the docstring in that file.
   - `src/components/layout/FeedbackButton.tsx` and `src/pages/FeedbackPage.tsx` are
     hand-built: feedback is two inputs about the product, not a register module. Its
     dropdowns still come from picklists (rule 4).
   - `src/components/admin/metadata/*` is hand-built, because it is the UI that **edits**
     the register. Rendering the field editor from the field register would mean the
     register describing itself, and a broken row would take away the screen needed to fix
     it. The exception is scoped to that folder; see `shared.tsx`.
4. **Never hardcode a picklist.** Options come from `spec/picklists.json`. Administration's
   roles are seeded into PostgreSQL *from* those same keys, so the two agree. Since Round 6
   `picklists.json` is itself generated from the `picklists` / `picklist_values` tables —
   change a dropdown in Administration and publish, never by editing the file.
5. **Every screen carries the prototype watermark.** A persistent banner:
   `PROTOTYPE — data is stored in this browser only. Not a live system.`
   Suppressed on Administration only, where the sentence would be false — see
   `src/components/layout/PrototypeBanner.tsx`.
6. **Automation is simulated, never real.** No emails, no webhooks, no timers that act. Write
   an entry to the automation log instead.
7. **Price screens carry a second watermark:** `Price book rev4 · snapshot · do not quote from this.`

## Stack

React 18 + TypeScript · Vite · Tailwind + shadcn/ui · TanStack Query · Axios ·
Zustand with the persist middleware (localStorage) · MSW · React Router · Zod · date-fns

Match the production stack so the code carries forward. No other state library, no CSS
framework other than Tailwind.

## Where the truth lives

**Editable metadata source of truth: PostgreSQL.**
**Phase-1 frontend representation: the generated `spec/*.json` files.**
**Supported direction: PostgreSQL → generated JSON. Unsupported: JSON → PostgreSQL.**

Since Round 6, fields, picklists and stages are rows in PostgreSQL, edited in Administration
and written out by publishing. The frontend still *reads* the JSON — that is a deliberate
Phase-1 transitional arrangement, not a permanent one (see the note below the table).

| File | Contains | Where it comes from |
|---|---|---|
| `spec/fields.json` | Every field: module, api_name, label, type, section, order, capture stage, requirement, condition, visibility condition, blocks transition, computed formula, help text | **Generated from PostgreSQL** — `field_metadata`, on publish |
| `spec/picklists.json` | Every dropdown and its values | **Generated from PostgreSQL** — `picklists`, `picklist_values` |
| `spec/stages.json` | The ten stages, each one's Progression % / Probability % pair, owner roles | **Generated from PostgreSQL** — `stages` |
| `spec/extensions.json` | The sidecar: computed expressions, child-list shapes, list views, overrides | Hand-maintained. **Not** generated, not in the database |
| `spec/module_split.json` | The pipeline split | **Part generated.** `pipeline`, `ranges`, `stage_field`, `reassign` and `read_through.parent_of`/`parent_link` come from PostgreSQL; the per-field judgement blocks stay hand-authored |
| `spec/criteria.json` | Entry and exit criteria per stage, with enforcement | Still generated from the workbook |
| `spec/gates.json` | The three gates and their checklist items | Still generated from the workbook |
| `spec/seed/*.json` | Products, price matrix, leads, registrations. **Not users, accounts or contacts** — those live in PostgreSQL; see `backend/seed.py` and `backend/migrate_*.py` | Still generated from the workbook |

The three generated-from-PostgreSQL files are **build artefacts. Never hand-edit them.** An
edit there has no path back into the database and the next publish overwrites it. To change
the register, change it in Administration and publish. `criteria.json`, `gates.json` and the
seed files are still workbook output — **regenerate rather than hand-edit** those too.

**Phase 2 may drop the JSON hop** and serve metadata straight from an API to the frontend, at
which point these three files disappear. Nothing should be written that assumes the JSON
layer is permanent.

```
Administration UI → PostgreSQL → publish → regenerate → spec/*.json → frontend
```

## The domain in one page

**Pipeline.** Ten stages, 0 to 9. **Leads carry Stages 0–7. Deals carry Stages 8–9.**
A Lead converts to a Deal at Stage 7 and becomes read-only.

| Stage | Name | Progression | Probability |
|---|---|---|---|
| 0 | Connect | 5% | 5% |
| 1 | Demo Presentation | 15% | 10% |
| 2 | POC / Pilot | 25% | 20% |
| 3 | Prescription | 40% | 30% |
| 4 | RFP / RFI | 50% | 40% |
| 5 | Technical Evaluation | 70% | 55% |
| 6 | Commercial Evaluation | 85% | 70% |
| 7 | Close | 95% | 90% |
| 8 | Project Success | 100% | 100% |
| 9 | Expansion | 100% | 100% |

**Progression % and Probability % come from ONE table — the stage** (decided 13 Sep 2026,
`backend/app/progression.py`, migration 0022). The pair lives on the `stages` table, is
edited in Administration → Stages, and is always a multiple of 5. **Progression moves on our
work; Probability moves on the client's decisions.** Rules:
- Create, or any stage move (forward, skip, reversal), sets both numbers to the new stage's
  pair and clears any override.
- A person may change either number; a value that differs from the stage's is an override
  and needs `probability_override_justification__s<stage>` (label "Override Justification")
  in the same save, or the server refuses it. Values step in 5s. There is no per-stage copy
  of either number.
- Closed Lost sets Probability to 0; reopening restores the stage's value.
- **Paid POC / pilot:** marking a Lead's pilot Paid creates a Deal with status
  `POC_PILOT_DEAL` ("POC/Pilot Deal") at Stage 7 Close, Progression 95 / Probability 100,
  contract value = pilot fee, and the Lead becomes Converted. `POC_PILOT_DEAL` is a
  Deals-only value on the shared status picklist — hidden and refused on Leads and
  Opportunities. How the programme after a pilot is tracked (Expansion lead vs new logo)
  is a phase-2 decision; do not build it.
- Never reintroduce an evidence ladder, band midpoints, or automatic boosts. Nomination Bid
  and Incumbent Only are reasons to override, not uplifts. The 0016 progression ladder
  (`progression_criteria`, `rung_proof_conditions`) was removed for writing the same two
  numbers as the stage and losing to whichever ran last.

**Stages are states, not steps.** Skipping forward and moving backward are both legal, each
with a mandatory recorded reason.

**Four-layer transition check**, in order:
1 mandatory fields → 2 exit criteria of the current stage → 3 entry criteria of the target
stage → 4 gate status.

**Three gates**, each anchored to the *entry* of a stage so that a skip cannot bypass them:

| Gate | Fires on entering | Passes when |
|---|---|---|
| G1 POC Brief | Stage 2 | 11 checklist items pass and 3 signatures are recorded |
| G2 Commit to Bid | Stage 4 | 9 elements assessed, then an approval decision |
| G3 Commercial | Stage 7 | 6 red lines clear and every threshold breach approved |

**A gate is a record with checklist children, not a checkbox.** It has status, outcome,
approver, a self-approval flag, conditions and evidence.

**Roles, not teams.** One person can hold every role. Today the CEO holds all commercial
roles, so approvals resolve to the submitter — record that honestly with a `self_approval`
flag and a visible modal. Never hide it.

**Two-party accounts.** End Client and Customer (Partner / SI) are different organisations on
the same deal. `Pre-Bid Alliance Partner` is a third, separate field — the partner who
*sourced* the deal is not always the partner you *bid with*.

**Money.** `TCV = (ARR × Years) + Perpetual Licence Fee + One-Time + 3rd-Party One-Time +
(3rd-Party Recurring × Years)`. Gross margin **excludes** third-party content.

**One revenue source per module, no fallbacks** (frozen 13 Sep 2026, `backend/app/revenue.py`):
Leads → `estimated_value` · Opportunities → `total_value_tcv` · Deals → `contract_value`. A blank
value counts as $0 and is flagged — never substitute another field. Pipeline totals count Open and
On Hold **primary** pursuits only (a Pursuit Group's secondaries never roll up, Playbook §7.2), in
USD at `fx_rate_at_entry` = local units per 1 USD. `total_project_value` is never revenue. Third-party is
capped at 40% of TCV. Never discount the platform licence without approval.

**Products are priced on a matrix** of catalogue item × T-shirt size (XS to Unlimited), then
multiplied by a region factor. Six categories: Modules, Segment Libraries, User Packs,
Add-Ons, Services, Support. Discounts apply **per category**, not per line.

## In scope for the prototype

Leads (all 8 stages) · Accounts · Contacts · Products · Quotes · Deals · the three gates ·
approvals queue · dashboard with real prototype data.

## Out of scope — do not build

Reports · Administration CRUD · Activities and Documents beyond a stub · the POC workspace
(weekly logs, issue register, close-out report) · partner scorecards ·
role-based permissions beyond "signed in with any role" / "is admin" / "is developer" (feedback only) ·
file upload to anywhere real · **comment pins** (dropped 18 Sep 2026 — see above) ·
**a Settings screen** (deleted 18 Sep 2026 — see below).

*(Authentication was on this list. It shipped in Phase 1 — see the note at the top.)*

**There is no Settings screen, and "Reset demo data" is gone.** Deleted 18 Sep 2026. It cleared
the browser store and reseeded it, which stopped meaning anything once every module a user can
reach moved to PostgreSQL — the button's own promise, "clears every record created or edited in
this browser", had become false for Leads, Opportunities, Deals, Accounts, Contacts and
Registrations alike. Its one remaining job was refreshing a stale copy of the CATALOGUE, and
that is fixed at the source instead: **products, prices, sizes, the rate card, support tiers,
regions and pricing params are read from `spec/seed/*.json` on every request** and never
persisted (`referenceCollection()` in `src/lib/spec/seed.ts`). MSW refuses writes to them with
405 — edit the file. Do not reintroduce a reset, and do not put reference data back in the
store; `useDataStore` no longer has a `reset()` to call.

## How reviewers tell us things

**Feedback is the built channel** (17 Sep 2026). A message icon in the top bar: anyone with a
role sends a category and a message, the page they were on is captured with it, and only a
DEVELOPER can read the queue — enforced in `app/auth.py::require_developer`, never by hiding a
screen. `/api/feedback`, table `feedback`. This is the one that works; use it.

**Comment pins were dropped, 18 Sep 2026.** Field-level notes anchored to a module and an
api_name, exported to CSV. They never got past an empty `comments` array and an id prefix — no
component, no endpoint, no export — and Feedback now covers the same job. The precision they
would have added is real (*"this label is wrong", against `leads.budget_estimate`*), so if they
come back, **build them in PostgreSQL, not the browser store**: on the store every reviewer's
notes live in one browser and the CSV only ever holds one person's.

**The automation log is still unbuilt**, and is now the only thing left on this list. A dockable
panel listing every automation that *would* have fired, with timestamp, type and target;
reviewers correct those entries and the corrections become Phase 3 requirements. Three comments
in the code describe it (`AcknowledgeDialog.tsx`, `PursuitBanner.tsx`, `models.py`) and nothing
implements it. It is worth deciding explicitly whether it ships or goes the way of the pins —
an unbuilt feature named here reads as a commitment to whoever opens this file next.

## Conventions

- Criterion codes: `E4.1` entry at Stage 4, `X3.2` exit at Stage 3
- Gate item codes: `CTB-01…09`, `POC-01…11`, `RL-01…06`
- Record ids: `LEAD-00118`, `DEAL-00031`, `QT-00087-R0`, `REG-00042`, `GATE-0091`
- Currency: enter local, report USD, stamp the FX rate
- Dates display as `dd MMM yyyy`
- Money displays with thousands separators and no decimals

## Dialog and message copy

Approved 17 Sep 2026. Every dialog, banner and server refusal a user can see follows these:

1. **Title asks or acts** — "Is this the same project?", never "Duplicate pursuit detected".
2. **One short lead sentence** saying what happened.
3. **Bullets, one idea each**, about 15 words at most. Never one long sentence stitched with dashes.
4. **No system words** — no record ids, api_names, "read-only record", "audit trail",
   "read-through", "per-stage", "custom_fields". Criterion codes only as a side tag.
5. **Buttons name the result** — "Move to Stage 5", "Join this group". Never "OK" / "Confirm".
6. **Errors say what to do next.**

**Readable is not roomy.** Keep the existing spacing; bullets sit tight under the lead.

Server refusals are `{code, message, details?}` built with `backend/app/messages.py` — the
wording lives there, once. The frontend branches on `code`, never on the words, and renders
every failure through `<ErrorNotice>` / `<Notice>` / `<Bullets>` in
`src/components/ui/notice.tsx` (shape normalised by `src/lib/errors.ts`).

## Working style

Direct answers. Flag gaps honestly rather than reassuring. When something in the spec looks
wrong, say so before building it.
