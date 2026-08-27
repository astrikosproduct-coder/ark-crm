# ARK CRM — clickable prototype

> Copy this file to the root of the prototype repo as `CLAUDE.md`.
> Claude Code loads it automatically at the start of every session.

## What this repo is

A **clickable prototype** of ARK CRM, an in-house CRM for **Astrikos** — a MEA platform
company selling the **S!aP** suite into smart cities, datacentres, utilities, O&G and
industrial clients.

Its purpose is to find gaps in the field list and the business rules **before** the real
product is built. It is shown to BD and management as if it were a real product.

**It is not the real product.** There is no backend, no database, no authentication and no
workflow automation. Do not add any.

## Hard rules — do not break these

1. **No backend.** Never add Express, Next API routes, Prisma, or any server. Data lives in
   the browser.
2. **All data access goes through MSW.** Components call `/api/...` with Axios exactly as they
   will in production. MSW intercepts and answers from the store. This is what makes the
   prototype reusable as the Phase 1 frontend — never bypass it by reading the store directly
   from a component.
3. **Never hardcode a field.** Every form renders from `spec/fields.json`. If a field is
   missing from a screen, the fix is in the spec, not in a component.
4. **Never hardcode a picklist.** Options come from `spec/picklists.json`.
5. **Every screen carries the prototype watermark.** A persistent banner:
   `PROTOTYPE — data is stored in this browser only. Not a live system.`
6. **Automation is simulated, never real.** No emails, no webhooks, no timers that act. Write
   an entry to the automation log instead.
7. **Price screens carry a second watermark:** `Price book rev4 · snapshot · do not quote from this.`

## Stack

React 18 + TypeScript · Vite · Tailwind + shadcn/ui · TanStack Query · Axios ·
Zustand with the persist middleware (localStorage) · MSW · React Router · Zod · date-fns

Match the production stack so the code carries forward. No other state library, no CSS
framework other than Tailwind.

## Where the truth lives

| File | Contains |
|---|---|
| `spec/fields.json` | Every field: module, api_name, label, type, section, order, capture stage, requirement, condition, visibility condition, blocks transition, computed formula, help text |
| `spec/picklists.json` | Every dropdown and its values |
| `spec/stages.json` | The ten stages, probability bands, owner roles |
| `spec/criteria.json` | Entry and exit criteria per stage, with enforcement |
| `spec/gates.json` | The three gates and their checklist items |
| `spec/seed/*.json` | Accounts, contacts, users, products, price matrix, leads |

Generated from `ARK_CRM_Field_Register_Workbook_v4.xlsx`. **Regenerate rather than hand-edit.**

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
