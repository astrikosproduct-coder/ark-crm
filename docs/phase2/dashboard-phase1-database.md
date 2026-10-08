# Dashboard Phase 1 — database changes

28 Sep 2026 · branch `phase-2` · migrations `0040_sales_targets`, `0041_pipeline_snapshots`

## The three answers the brief asked for

| | |
|---|---|
| **Fiscal-year setting** | `FISCAL_YEAR_START_MONTH`, an environment variable in `backend/.env`, default `4`. Read in one place, `backend/app/fiscal.py`. The dashboard's quarter presets, target fiscal years and seed months all come from it. FY27 = 01 Apr 2026 – 31 Mar 2027, Q1 = Apr–Jun. |
| **Booked amount** | `deals.contract_value` (label *Contract Value*, reported as *Actual Revenue*). There is no fallback. |
| **Booked date** | `deals.po_received_date` (*PO Received Date*), not Booking Date. See item 4 below. |

## What was built

1. **`sales_targets`**: one row per BD Owner × month, USD, `DRAFT → LOCKED`. A locked target changes only through a revision: a new locked row with `revision_of` and a required note. The old row becomes `SUPERSEDED` and keeps its number. The database enforces this with trigger `trg_sales_targets_guard` and partial unique index `uq_sales_targets_current`, so a raw SQL write is refused too. Company target for FY27 = `sum(target_amount_usd) WHERE fiscal_year = 'FY27' AND status <> 'SUPERSEDED'`.
2. **`pipeline_snapshots`**: one row for all, then one per BD Owner, per Booking Region and per Segment, never crossed. Insert-only (trigger), and one run per day (`UNIQUE NULLS NOT DISTINCT`).
3. **Month-end job**: runs inside the API at 23:55 IST on each month's last day (`app/pipeline_snapshots.py`). The first start after deployment writes the starting snapshot. Manual route: `POST /api/pipeline-snapshots`.
4. **API** (no UI): `GET/POST /api/sales-targets`, `PATCH /api/sales-targets/{id}`, `POST …/{id}/lock`, `POST …/{id}/revise`, `GET /api/pipeline-snapshots`.
5. **Seed**: `backend/seed_sales_targets.py --actor <email> [--apply]` creates 12 drafts at 0 for each active BD Owner. It is safe to run again.

Forward and rollback were both run on a copy of the development database. The full backend suite passes (26 scripts, including parity before and after). A column-by-column comparison against the unmigrated database shows **no column added to any existing table**.

## Item 4: no new fields, and what the brief assumed

- **Booked amount is Contract Value, not "Final Negotiated Value, else TCV".** The project froze one revenue field per module with no fallbacks on 13 Sep 2026, and a Deal's is Contract Value. Final Negotiated Value is an Opportunity field. Rule X6.1 already refuses to convert an Opportunity until Final Negotiated Value equals its TCV, so the brief's pair is one number before a Deal exists.
- **Booking Date is not the booked date here.** Decided 15 Sep 2026: a deal is won the day its PO arrives, `po_received_date`, and the dashboard's Won tile counts by it. Booking Date is the finance/ERP booking and lags the PO. Booking Date is still captured and Mandatory at Stage 7, and is required to leave Stage 8.
- **"Booking Date mandatory as soon as Order Booked = Yes" was not added.** Decided 21 Sep 2026: required fields are demanded when a record *leaves* a stage, not on every save. To demand it when leaving Stage 7 instead of Stage 8, set its *Mandatory from* to 7 in Setup and publish. That needs no code or schema change.
- **Closed Lost Reason Code is already enforced** on Leads, Opportunities and Deals. Checked: a save to Closed Lost without a reason is refused (422), and one with a reason goes through. The reason is kept per stage.
- **Customer Class, Account Target Phase, Partner Tier, Partner Type**: a data-entry task, with no schema change. I could not confirm the "60 imported accounts": the development database holds 1 account, and production started empty on 21 Sep. The 60 must be in production.

## Where I departed from the brief (project convention wins)

| Brief | Built | Why |
|---|---|---|
| `sales_target`, `pipeline_snapshot` | `sales_targets`, `pipeline_snapshots` | Tables are plural here. |
| `id` | `target_id` = `TGT-00001`; snapshots `id` integer | Reference ids like `FB-`/`LEAD-` for rows people refer to; integer for bulk history, as `audit_log`. |
| status `draft \| locked` | `DRAFT \| LOCKED \| SUPERSEDED`, varchar + CHECK | Upper-case keys, no Postgres enums, as every status here. `SUPERSEDED` lets the unique index know which row is current. |
| revision — status unspecified | the revision is created `LOCKED` | A locked number changes only by a noted revision; a revision that could drift as a draft would undo the lock. |
| Sales Head / Admin write | **ADMIN or DEVELOPER** | No Sales Head role exists; decided 28 Sep 2026 not to add one. |
| "all sales roles" read | anyone with a role | Permissions are "has any role" until the RBAC phase. |
| unique on (date, owner, region, segment) | adds `dimension` | Without it NULL means both "all regions" and "no region recorded", and the two collide. |
| — | `unpriced_count`, `created_by` on snapshots | Records counted at $0 for want of a value or FX rate are flagged, as on the dashboard; `created_by` is NULL for the timer. |
| weighted = value × stage probability | value × the record's **own** Probability % | Same as the dashboard tile: the stage's number unless someone overrode it with a justification. |
| `deal_count` of open deals | counts open **Leads and Opportunities** | Here "pipeline" is pre-Deal; Deals are sold work. Name kept as asked. |
| backfill by re-run | today, or a missed month-end up to 7 days late | A past day's pipeline cannot be rebuilt from live rows. A late run records today's figures under that date, and `created_at` shows how late. |
| a configurable setting | environment variable, not a table | No settings table exists. Setup's (unbuilt) *Fiscal Year* item is where it moves; one function changes. |
| audit | `app/audit.py` from the API and seed | The audit trail is written by the application, not by triggers. A raw SQL write bypasses the audit, but not the lock. |
| scheduled job | a timer inside the API | Hard rule 6 forbids timers that act; this one is recorded there as the single exception (28 Sep 2026). |

## Things to know

- **Region filters disagree.** Snapshots split by **Booking Region**, as asked. The live dashboard's Region filter reads **Destination Region**. Pick one before the charts are built, or the Pipeline tab will compare two different splits.
- **No BD Owners exist yet** in development, so the seed has nothing to create. Run it after users hold the BD Owner role.
- **Don't change the fiscal start month once targets exist.** Each target stores its fiscal year label.
- **A draft cannot be deleted through the API.** The database allows deleting a draft, and a locked or superseded target is never deleted.
