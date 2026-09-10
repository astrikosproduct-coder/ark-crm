# ARK CRM — clickable prototype

> Copy this file to the root of the prototype repo as `CLAUDE.md`.
> Claude Code loads it automatically at the start of every session.

## What this repo is

A **clickable prototype** of ARK CRM, an in-house CRM for **Astrikos** — a MEA platform
company selling the **S!aP** suite into smart cities, datacentres, utilities, O&G and
industrial clients.

Its purpose is to find gaps in the field list and the business rules **before** the real
product is built. It is shown to BD and management as if it were a real product.

**It is not the real product.** There is no authentication and no workflow automation — do
not add either. It is *mostly* browser-only: Round 1 moved users, accounts and contacts onto
a real FastAPI + PostgreSQL backend, and every other module is still MSW over `localStorage`.
See hard rule 1 for exactly which is which.

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
   | Dynamic admin-field values | `custom_fields` JSONB on accounts, contacts, leads, opportunities, deals | the module's own endpoint |
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
| `spec/stages.json` | The ten stages, probability bands, owner roles | **Generated from PostgreSQL** — `stages` |
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

| Stage | Name | Probability |
|---|---|---|
| 0 | Connect | 0–10% |
| 1 | Demo Presentation | 10–20% |
| 2 | POC / Pilot | 20–40% |
| 3 | Prescription | 30–50% |
| 4 | RFP / RFI | 40–60% |
| 5 | Technical Evaluation | 50–70% |
| 6 | Commercial Evaluation | 60–80% |
| 7 | Close | 90–100% |
| 8 | Project Success | 100% |
| 9 | Expansion | — |

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
(3rd-Party Recurring × Years)`. Gross margin **excludes** third-party content. Third-party is
capped at 40% of TCV. Never discount the platform licence without approval.

**Products are priced on a matrix** of catalogue item × T-shirt size (XS to Unlimited), then
multiplied by a region factor. Six categories: Modules, Segment Libraries, User Packs,
Add-Ons, Services, Support. Discounts apply **per category**, not per line.

## In scope for the prototype

Leads (all 8 stages) · Accounts · Contacts · Products · Quotes · Deals · the three gates ·
approvals queue · dashboard with real prototype data.

## Out of scope — do not build

Reports · Administration CRUD · Activities and Documents beyond a stub · the POC workspace
(weekly logs, issue register, close-out report) · partner scorecards · real authentication ·
role-based permissions · file upload to anywhere real.

## Two features that are the actual deliverable

**Automation log.** A dockable panel listing every automation that *would* have fired, with
timestamp, type and target. Reviewers correct these, and their corrections are Phase 3
requirements.

**Comment pins.** Click any field label to leave a note. Records module, field api_name,
comment and author. Exports to CSV. This is how the prototype pays for itself.

## Conventions

- Criterion codes: `E4.1` entry at Stage 4, `X3.2` exit at Stage 3
- Gate item codes: `CTB-01…09`, `POC-01…11`, `RL-01…06`
- Record ids: `LEAD-00118`, `DEAL-00031`, `QT-00087-R0`, `REG-00042`, `GATE-0091`
- Currency: enter local, report USD, stamp the FX rate
- Dates display as `dd MMM yyyy`
- Money displays with thousands separators and no decimals

## Working style

Direct answers. Flag gaps honestly rather than reassuring. When something in the spec looks
wrong, say so before building it.
