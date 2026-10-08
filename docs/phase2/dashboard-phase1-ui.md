# Dashboard Phase 1 — UI and queries

28 Sep 2026 · branch `phase-2` · builds on `dashboard-phase1-database.md`

## What changed

- **Five tabs:** Performance, Pipeline, Partners, Accounts, Win & loss. The Overview tab is gone.
- **Removed, with their queries and components:**
  - Expected revenue by close month
  - Overall RAG
  - Time in current stage
  - Due in the next 30 days
  - Red and stuck
  - The old Pipeline by stage and Why we lose, replaced by Stage funnel and the new Why we lose.
- **The five KPI cards are unchanged**, now the first row of Performance. I compared them with the previous code under six filter states and found no differences.
- **One filter row** is shared by every tab: Period, Booking Region, Segment, BD Owner, Opportunity Type, Theme, Partner and Deal Source. It persists across tab switches and reaches every tile.
- **The page opens on the current fiscal year** (decided 28 Sep 2026). Period now offers this and last fiscal year, as well as quarters.
- **Every tile is a config object** (`frontend/src/components/dashboard/config.ts`) matched by a server definition (`TILES` in `backend/app/routers/dashboard.py`: population × dimension). A later widget builder can produce the same objects without rewriting the components.
- **Clicking a bar, slice, point or meter** opens the records behind it (`GET /api/dashboard/records`). The server groups them with the same code, so the list adds up to the mark.

## Where the project won over the brief

| Brief | Built | Why |
|---|---|---|
| Booked ties to Won **and** Actual Revenue (Deals) | Ties to **Won** exactly. It cannot tie to Actual Revenue. | The Actual Revenue card counts Deals by Expected Close Month; Booked counts by PO Received Date. Both cards had to stay unchanged. The Booked line is Won, month by month, and its year total is printed under the chart. |
| Open pipeline excludes On Hold | **On Hold included** | The Open pipeline card counts Open and On Hold (project rule) and had to stay identical. Every tile must add up to it. |
| Weighted = value × stage probability % | value × the record's **own** Probability % | That is the card's rule. It equals the stage's number unless someone overrode it with a justification. |
| Row-level permissions: BD owners see their own deals | **None** | The project has none; everyone with a role sees every pursuit until the RBAC phase. |
| Pre-aggregated queries, not one per tile | **One request** reads each table once and computes every tile | Decided 21 Sep 2026: at hundreds to low thousands of records, Python-side aggregation is the rule. Month-end history reads the pre-aggregated `pipeline_snapshots`. |
| Palette page, card, inset, text and border colours | **Series colours added as new tokens**; surfaces and text keep the app's own tokens | You asked (28 Sep 2026) that no existing colour be changed. |
| A charting library | Hand-built SVG and Tailwind, as the page already was | No chart library is installed; the existing widgets were hand-built. |
| Target line under any filter | Drawn with no filter or a BD Owner filter only | Targets are stored per owner × month only. Under a Region, Segment, Theme, Deal Source, Partner or Opportunity Type filter the tile says why no line is drawn. |
| Donut by Theme (7 values) | The first four values take fixed colours; the rest fold into a hatched "Other" | Colours are fixed per value, never per rank. Crimson is kept for loss, and the table view lists every theme. |
| Clicking any mark opens its records | Every tile except "Open pipeline at each month-end" | Snapshots keep totals, not records. The tile's ⓘ says so. |

## Definitions as built

- **Forecast** is Booked to date plus the weighted value of open records by Expected Close Month.
  - "Open" means pipeline plus counted Deals whose PO has not arrived.
  - The line joins Booked at the current month. The current month's still-open value is added at the next point.
  - A record whose close month has passed, or who has none, is left out, and the ⓘ counts them.
- **Quarter meters:** an ended quarter is measured on Booked ÷ Target; an open or future one on Forecast ÷ Target. A quarter with no target shows "No target set".
- **Close-month chart:** the next six months within the period, plus a "No month" column. Records closing earlier or later are counted under the chart.
- **Month-end history** uses the latest snapshot in each month. It can be cut one way at a time: all, one BD Owner, one Booking Region or one Segment. Under any other filter it says so rather than guess.
- **Partner** is Customer (Partner / SI). A Deal uses its own locked copy.
- **Region** is Booking Region everywhere money is measured. Destination Region appears only on "Pipeline by delivery region".

## Things to know

- **Opening on the fiscal year changes the default Open pipeline card.** With a period set, records with no Expected Close Month are left out of the card, as any range has always done. The Period ⓘ counts them and the Pipeline tab shows them under "No month".
- **Colour-blind separation:** the mandated series hex values fail the dataviz validator's lightness and chroma checks. With the categorical order used (navy, teal, amber, plum), colour-blind separation passes in both themes. Dark navy and teal sit just under the normal-vision floor (ΔE 13.8 against 15). Every chart therefore also has legend labels, 2px gaps, dash patterns and its table view. Contrast passes: every series is at least 3:1 and axis text at least 4.8:1 in both themes.
- **The old `--chart-*` tokens are now unused.** They were left in place, as asked.
