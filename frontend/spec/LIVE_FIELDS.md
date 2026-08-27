# ARK CRM — live field reference

> **PROTOTYPE — data is stored in this browser only. Not a live system.**

Partners · Accounts · Contacts · Leads · Opportunities · Deals — every field the prototype renders today, with its type, its picklist options and, for a child list, every column of one row.

Generated on 2026-08-27 by running the application's own spec loader, not a copy of it — `npm run spec:fields`. The workbook remains the source; `spec/fields.json` is never hand-edited.

**What "live" means here.** A field is listed if the form engine puts it on a screen. Four rules shape the list:

- The pipeline is **three modules**, not two. `spec/module_split.json` is the authority on which module owns which stage, and every field follows the stage that captures it. The **Carry** column on each pipeline table says how the field got there — see the key below.
- Fields the register writes flat but which really describe **one row of a child list** — the four `milestone_—_*` dates, the seven `guarantee_—_*` fields — are listed **only** under their child list. The form engine drops them as record fields, because rendering them both ways gave two places to type the same value and only one of them was kept.
- Picklist options are the **active** ones, in the register’s own sort order, shown as labels. Full key → label sets are in Appendix A.
- **Requirement** and **Stage** are the register’s own `requirement` and `capture_stage` columns. `any` means the field applies at every stage; `—` means the register records no stage.

**Carry** — how a field came to be on the module it is on:

| Carry | Meaning |
|---|---|
| — | The register writes it on this module and it stayed. |
| moved | Reassigned by capture stage. A Stage 5 field is an Opportunity field wherever the workbook filed it. |
| shared | A CROSS-CUTTING or SYSTEM field, placed on all three pipeline modules. A skip reason is as true of an Opportunity as of a Lead. |
| own instance | Per-record state. An Opportunity at Stage 5 and the Lead it came from at Stage 3 are two different stages, not a copy. |
| read-through | **Resolved from the parent record and never stored here.** Identity is carried by reference, so the same End Client cannot exist in three places and drift. |
| NEW | Declared in `extensions.json` `new_fields` — the register does not carry it. Listed on Spec Health as a gap-fix or a structural link. |

## Modules at a glance

| Module | Stages | Live record fields | Child lists | Child-list columns | Sections |
|---|---|---|---|---|---|
| **Partners** | — | 34 | 0 | 0 | 3 |
| **Accounts** | — | 19 | 0 | 0 | 4 |
| **Contacts** | — | 15 | 0 | 0 | 2 |
| **Leads** | 0–3 | 77 | 2 | 8 | 8 |
| **Opportunities** | 4–6 | 95 | 1 | 8 | 9 |
| **Deals** | 7–9 | 88 | 3 | 15 | 10 |

Row counts match the target placement in `ARK_CRM_Field_Register_Split_v1.xlsx`: Leads 77, Opportunities 99, Deals 95 — counting every row on the sheet, including the child-column rows the form engine folds into their table.

---

## Partners

### DEAL REGISTRATION

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Registration ID | `registration_id` | autonumber | System | — | REG-00001 |
| Partner | `partner` | lookup | **Mandatory** | — | → `account` |
| End Client | `end_client` | lookup | **Mandatory** | — | → `account` |
| Project Name | `project_name` | text | **Mandatory** | — | max 150 |
| Estimated Value | `estimated_value` | currency | **Mandatory** | — | — |
| Expected Timeline | `expected_timeline` | text | **Mandatory** | — | max 100 |
| Partner Role | `partner_role` | picklist | **Mandatory** | — | `partners__partner_role` — Prime · Sub |
| Submitted Date | `submitted_date` | date | **Mandatory** | — | — |
| Acknowledged Date | `acknowledged_date` | date | **Mandatory** | — | — |
| Acknowledgement SLA Met | `acknowledgement_sla_met` | computed | Computed | — | `acknowledged_date <= add_days(submitted_date, 2)` |
| Exclusivity Start Date | `exclusivity_start_date` | date | **Mandatory** | — | — |
| Exclusivity Expiry Date | `exclusivity_expiry_date` | computed | Computed | — | `add_days(exclusivity_start_date, 89)`<br>Start date plus 90 days |
| Registration Status | `registration_status` | picklist | **Mandatory** | — | `partners__registration_status` — Submitted · Acknowledged · Active · Extended · Expired · Superseded · Rejected |
| Extension Reason | `extension_reason` | text | Conditional | — | max 500 |
| Linked Lead | `linked_lead` | lookup | Optional | — | → `lead` |

### CONFLICT ADJUDICATION

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Conflict ID | `conflict_id` | autonumber | System | — | CNF-00001 |
| Registration A | `registration_a` | lookup | **Mandatory** | — | → `deal_registration` |
| Registration B | `registration_b` | lookup | **Mandatory** | — | → `deal_registration` |
| Who Registered First | `who_registered_first` | text | **Mandatory** | — | max 300 |
| Stronger Client Relationship | `stronger_client_relationship` | text | **Mandatory** | — | max 300 |
| Better Delivery Capability | `better_delivery_capability` | text | **Mandatory** | — | max 300 |
| Decision | `decision` | picklist | **Mandatory** | — | `partners__decision` — Awarded to Registration A · Awarded to Registration B · Both declined |
| Decision Date | `decision_date` | date | **Mandatory** | — | — |
| Decided By | `decided_by` | lookup | **Mandatory** | — | → `user` |
| Both Partners Notified | `both_partners_notified` | checkbox | **Mandatory** | — | — |

### QUARTERLY SCORECARD

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Scorecard ID | `scorecard_id` | autonumber | System | — | SC-00001 |
| Partner | `partner` | lookup | **Mandatory** | — | → `account` |
| Quarter | `quarter` | picklist | **Mandatory** | — | `partners__quarter` — Q1 · Q2 · Q3 · Q4 plus year |
| Leads Registered | `leads_registered` | computed | Computed | — | **no formula in the register** |
| Conversion Rate to Stage 4+ | `conversion_rate_to_stage_4+` | computed | Computed | — | **no formula in the register** |
| Revenue Closed | `revenue_closed` | computed | Computed | — | **no formula in the register** |
| Partner Satisfaction Score | `partner_satisfaction_score` | number | **Mandatory** | — | — |
| Platform Depth | `platform_depth` | multi-select | Optional | — | **No value set named in the register** — see Spec Health |
| QBR Date | `qbr_date` | date | Optional | — | — |

---

## Accounts

### CORE

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Account ID | `account_id` | autonumber | System | — | ACC-00001 |
| Account Name | `account_name` | text | **Mandatory** | — | max 150 |
| Account Type | `account_type` | multi-select | **Mandatory** | — | `accounts__account_type` — End Client · Partner / SI · Consultant / Specifier · OEM / Technology Partner · Sector Specialist |
| Account Owner | `account_owner` | lookup | **Mandatory** | — | → `user` |
| Region | `region` | picklist | **Mandatory** | — | `region` — India · MEA · APAC · Americas |
| Website | `website` | url | Optional | — | — |
| Phone | `phone` | text | Optional | — | max 30 |
| Address | `address` | long text | Optional | — | — |

### CLASSIFICATION

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Segment | `segment` | picklist | **Mandatory** | — | `segment` — Infrastructure · Industry · Power · Mobility |
| Customer Class | `customer_class` | picklist | **Mandatory** | — | `customer_class` — A Strategic (>$2M) · B Commercial ($250K-$2M) · C/D Transactional (<$250K) |
| Account Target Phase | `account_target_phase` | picklist | **Mandatory** | — | `accounts__account_target_phase` — Year 1 · Year 2 · Year 3 · Not targeted |

### PARTNER ATTRIBUTES

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Partner Tier | `partner_tier` | picklist | Conditional | — | `accounts__partner_tier` — Tier 1 Strategic · Tier 2 Commercial · Registered · Not a partner |
| Partner Type | `partner_type` | picklist | Conditional | — | `accounts__partner_type` — Strategic MSI · Systems Integrator · OEM / Technology · Sector Specialist |
| Platform Depth | `platform_depth` | multi-select | Optional | — | **No value set named in the register** — see Spec Health |
| Partner Satisfaction Score | `partner_satisfaction_score` | number | Optional | — | — |
| Engagement Cadence | `engagement_cadence` | picklist | Conditional | — | `accounts__engagement_cadence` — Monthly · Bi-monthly · Deal-specific only |

### RESEARCH

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Client Digital Strategy | `client_digital_strategy` | long text | Optional | — | — |
| Known OT / IT Stack | `known_ot_it_stack` | long text | Optional | — | — |
| Active Tenders | `active_tenders` | long text | Optional | — | — |

---

## Contacts

### CORE

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Contact ID | `contact_id` | autonumber | System | — | CON-00001 |
| Full Name | `full_name` | text | **Mandatory** | — | max 100 |
| Job Title | `job_title` | text | **Mandatory** | — | max 100 |
| Account | `account` | lookup | **Mandatory** | — | → `account` |
| Email | `email` | email | Optional | — | — |
| Phone | `phone` | text | Optional | — | max 30 |
| Mobile | `mobile` | text | Optional | — | max 30 |
| LinkedIn | `linkedin` | url | Optional | — | — |

### ROLE & RELATIONSHIP

| Label | api_name | Type | Requirement | Stage | Options / target / formula |
|---|---|---|---|---|---|
| Contact Role | `contact_role` | picklist | **Mandatory** | — | `contacts__contact_role` — DECM Decision Maker · RECM Recommender · INFL Influencer · INTEL Intel Provider · GENL General Contact |
| Engagement Owner | `engagement_owner` | lookup | **Mandatory** | — | → `user` |
| Relationship Score | `relationship_score` | number | Conditional | — | — |
| Friend / Foe Assessment | `friend_foe_assessment` | picklist | Optional | — | `contacts__friend_foe_assessment` — Supporter · Neutral · Blocker |
| Confidential | `confidential` | checkbox | System | — | — |
| Is Client POC Evaluator | `is_client_poc_evaluator` | checkbox | Optional | — | — |
| Notes | `notes` | rich text | Optional | — | — |

---

## Leads

Stages 0–3.

### HEADER

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Progression % | `progression_pct` | computed | Computed | any | resolved by `progression` — see lib/spec/resolvers.ts<br>0 · 11 · 22 · 33 · 44 · 56 · 67 · 78 · 89 · 100 | NEW |

### STAGE 0 — CONNECT

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Lead ID | `lead_id` | autonumber | System | 0 | LEAD-00001 | — |
| Opportunity Name | `opportunity_name` | text | **Mandatory** | 0 | max 150<br>Format: [Project Name] — [Client] | — |
| Region | `region` | picklist | **Mandatory** | 0 | `region` — India · MEA · APAC · Americas | — |
| End Client | `end_client` | lookup | **Mandatory** | 0 | → `account`, filtered: _Account Type must include End Client_<br>Account Type must include End Client | — |
| Customer (Partner / SI) | `customer_partner_si` | lookup | **Mandatory** | 0 | → `account`, filtered: _Account Type must include Partner / SI_<br>Account Type must include Partner / SI | — |
| BD Owner | `bd_owner` | lookup | **Mandatory** | 0 | → `user`, filtered: _Role must include BD Owner_<br>Role must include BD Owner | — |
| Primary Contact | `primary_contact` | lookup | Optional | 0 | → `contact` | — |
| Deal Source | `deal_source` | picklist | **Mandatory** | 0 | `leads__deal_source` — Partner-sourced · Direct | — |
| Opportunity Type | `opportunity_type` | picklist | **Mandatory** | 0 | `leads__opportunity_type` — New Logo · Expansion · Renewal | — |
| Partner Deal Registration | `partner_deal_registration` | lookup | Conditional | 0 | → `deal_registration`<br>shown when `deal_source == 'Partner-sourced'` | — |
| Segment | `segment` | picklist | **Mandatory** | 0 | `segment` — Infrastructure · Industry · Power · Mobility | — |
| Theme | `theme` | picklist | **Mandatory** | 0 | `theme` — Smart Cities · Energy Utilities & Critical Infrastructure · Smart Buildings & Campuses · Industry 4.0 & Manufacturing · Data Centers · Defence & Protected Markets · Smart Transport & Infrastructure | — |
| S!aP Solution Suite | `sap_solution_suite` | lookup | **Mandatory** | 0 | → `product`, filtered: _Suite Type must be Primary suite_<br>Suite Type must be Primary suite | — |
| Lead Stage | `project_stage` | picklist | **Mandatory** | 0 | **Derived from the module range, not from `leads_stage`** — 0 Connect · 1 Demo Presentation · 2 POC / Pilot · 3 Prescription | — |
| Lead Status | `lead_status` | picklist | **Mandatory** | 0 | `leads__lead_status` — Open · On Hold · Closed Lost · Converted | — |
| Probability (%) | `probability_pct` | number | **Mandatory** | 0 | Must sit in the band for the current stage | — |
| Expected Close Month | `expected_close_month` | date | **Mandatory** | 0 | — | — |
| Currency | `currency` | picklist | **Mandatory** | 0 | `leads__currency` — USD · AED · SAR · QAR · OMR · KWD · BHD | — |
| FX Rate at Entry | `fx_rate_at_entry` | number | System | 0 | Rate to USD | — |
| Estimated Value | `estimated_value` | currency | **Mandatory** | 0 | — | — |
| Is Primary Pursuit | `is_primary_pursuit` | checkbox | **Mandatory** | 0 | Default true | — |
| Parent Pursuit | `parent_pursuit` | lookup | Conditional | 0 | → `lead`<br>shown when `is_primary_pursuit == false` | — |
| Parent Deal | `parent_deal` | lookup | Conditional | 0 | → `deal`<br>shown when `opportunity_type == 'Expansion'` | — |
| Incremental Value | `incremental_value` | currency | Conditional | 0 | shown when `opportunity_type == 'Expansion'` | — |
| Contracting Party | `contracting_party` | computed | Computed | 0 | `deal_source == 'Partner-sourced' ? customer_partner_si : end_client`<br>Customer (Partner / SI) where Deal Source = Partner-sourced, otherwise End Client | — |
| Remarks / Notes | `remarks_notes` | rich text | **Mandatory** | 0 | — | — |
| Lighthouse Project | `lighthouse_project` | checkbox | Optional | 0 | — | — |
| Gorilla Flag | `gorilla_flag` | checkbox | Optional | 0 | — | — |
| Demo Agreed | `demo_agreed` | checkbox | **Mandatory** | 0 | — | — |
| Demo Scheduled Date | `demo_scheduled_date` | date | **Mandatory** | 0 | — | — |
| Demo Completed | `demo_completed` | checkbox | **Mandatory** | 0 | — | — |

### STAGE 1 — DEMO PRESENTATION

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Demo Date | `demo_date` | date | **Mandatory** | 1 | — | — |
| Suite Demonstrated | `suite_demonstrated` | lookup | **Mandatory** | 1 | → `product` | — |
| Demo Attendees | `demo_attendees` | child list | **Mandatory** | 1 | row shape in the child-list table below | — |
| Interest Level | `interest_level` | picklist | **Mandatory** | 1 | `leads__interest_level` — High · Medium · Low | — |
| Agreed Next Step | `agreed_next_step` | picklist | **Mandatory** | 1 | `leads__agreed_next_step` — POC scoping · Prescription · RFP · Implementation · None | — |
| Data / Site Access Confirmation Document | `data_site_access_confirmation_document` | file | Conditional | 1 | required when `agreed_next_step == 'POC scoping'`<br>shown when `agreed_next_step == 'POC scoping'` | — |
| Pilot Commercial Model | `pilot_commercial_model` | picklist | Conditional | 1 | `leads__pilot_commercial_model` — Free · Paid<br>required when `agreed_next_step == 'POC scoping'`<br>shown when `agreed_next_step == 'POC scoping'` | — |
| Pilot Fee | `pilot_fee` | currency | Conditional | 1 | required when `agreed_next_step == 'POC scoping' && pilot_commercial_model == 'Paid'`<br>shown when `agreed_next_step == 'POC scoping' && pilot_commercial_model == 'Paid'` | — |
| Client Feedback | `client_feedback` | long text | **Mandatory** | 1 | — | — |
| Competitors Mentioned | `competitors_mentioned` | text | Optional | 1 | max 255<br>Free text. Was typed multiselect with no value set behind it in the register. | — |
| Feature Gaps Logged | `feature_gaps_logged` | child list | Optional | 1 | row shape in the child-list table below | — |
| Demo Debrief Notes | `demo_debrief_notes` | long text | **Mandatory** | 1 | — | — |

### STAGE 2 — POC / PILOT

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Secondary S!aP Suites | `secondary_sap_suites` | multi-select | **Mandatory** | 2 | **No value set named in the register** — see Spec Health | — |
| POC Record | `poc_record` | lookup | Conditional | 2 | → `poc` | — |
| POC Brief Gate | `poc_brief_gate` | lookup | **Mandatory** | 2 | → `gate`<br>Gate Type = POC Brief | — |

### STAGE 3 — PRESCRIPTION

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Consultant / Specifier | `consultant_specifier` | lookup | **Mandatory** | 3 | → `account` | — |
| Sales Owner | `sales_owner` | lookup | Optional | 3 | → `user`, filtered: _Role must include Sales Owner_<br>Role must include Sales Owner | — |
| Presales Owner | `presales_owner` | lookup | Optional | 3 | → `user`, filtered: _Role must include Presales Owner_<br>Role must include Presales Owner | — |
| Client Phase | `client_phase` | picklist | **Mandatory** | 3 | `leads__client_phase` — Solution design · Budgeting · Neither | — |
| Project Team Access Confirmed | `project_team_access_confirmed` | checkbox | **Mandatory** | 3 | — | — |
| Budget Estimate | `budget_estimate` | currency | **Mandatory** | 3 | — | — |
| Budget Confirmed | `budget_confirmed` | checkbox | **Mandatory** | 3 | — | — |
| Probable Award Date | `probable_award_date` | date | **Mandatory** | 3 | — | — |
| Pre-Bid Alliance Partner | `pre_bid_alliance_partner` | lookup | **Mandatory** | 3 | → `account`<br>shown when `deal_source != 'Direct'` | — |
| Alliance Structure | `alliance_structure` | picklist | **Mandatory** | 3 | `leads__alliance_structure` — Astrikos prime · Partner prime · Consortium / joint bid · Not applicable | — |
| PBAA Signed Date | `pbaa_signed_date` | date | **Mandatory** | 3 | shown when `deal_source != 'Direct'` | — |
| CTB Gate | `ctb_gate` | lookup | **Mandatory** | 3 | → `gate`<br>Gate Type = CTB | — |
| CTB Approval Status | `ctb_approval_status` | picklist | **Mandatory** | 3 | `leads__ctb_approval_status` — Not started · In progress · Approved · Approved with conditions · Deferred · No bid | — |
| CTB Approval Date | `ctb_approval_date` | date | **Mandatory** | 3 | — | — |
| Total Project Value | `total_project_value` | currency | Optional | 3 | shown when `alliance_structure == 'Partner prime'` | — |

### __header

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Overall RAG | `overall_rag` | picklist | Optional | any | `overall_rag` — Green · Amber · Red | NEW |
| Next Milestone | `next_milestone` | text | Optional | any | max 200 | NEW |
| Next Milestone Date | `next_milestone_date` | date | Optional | any | — | NEW |

### CROSS-CUTTING

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Probability Override Justification | `probability_override_justification` | text | Conditional | any | max 500 | — |
| Stage Skip Reason | `stage_skip_reason` | text | Conditional | any | max 500 | — |
| Stage Reversal Reason | `stage_reversal_reason` | text | Conditional | any | max 500 | — |
| Closed Lost Reason Code | `closed_lost_reason_code` | picklist | Conditional | any | `closed_lost_reason_code` — Lost to competitor · Price · Technical fit · Relationship · Client cancelled · Budget withdrawn · No bid · Partner conflict · Timing<br>shown when `lead_status == 'Closed Lost'` | — |
| On Hold Reason | `on_hold_reason` | text | Conditional | any | max 500<br>shown when `lead_status == 'On Hold'` | — |
| Close Date Pushback Count | `close_date_pushback_count` | computed | Computed | — | **no formula in the register** | — |
| Days in Current Stage | `days_in_current_stage` | computed | Computed | — | **no formula in the register** | — |
| Days Since Last Update | `days_since_last_update` | computed | Computed | — | **no formula in the register** | — |

### SYSTEM

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Created By | `created_by` | lookup | System | — | → `user` | — |
| Created Date | `created_date` | date-time | System | — | — | — |
| Modified By | `modified_by` | lookup | System | — | → `user` | — |
| Modified Date | `modified_date` | date-time | System | — | — | — |

### Leads — child lists

Each table below is **one row** of that child list.

#### `demo_attendees` — Demo Attendees

Row shape: _inferred_.

| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |
|---|---|---|---|---|---|
| Attendee | `attendee` | lookup | **required** | → `contact` | declared in extensions.json |
| Job Title | `job_title` | text | optional | max 100 | declared in extensions.json |
| Organisation | `organisation` | lookup | optional | → `account` | declared in extensions.json |
| Role | `attendee_role` | picklist | **required** | `contacts__contact_role` — DECM Decision Maker · RECM Recommender · INFL Influencer · INTEL Intel Provider · GENL General Contact | declared in extensions.json |

<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>

Derived from the field's own description ('The client and partner people who attended, with their roles') and its use_case ('a demo attended only by junior technical staff is a warning sign'). Attendee is a contacts lookup because a contact is the register's record for a client or partner person. Role reuses contacts__contact_role, the only role vocabulary the register gives a contact - it is a buying role (DECM/RECM/INFL) rather than a seniority scale, which is arguably not what the use_case is asking for. Job Title is captured on the ROW rather than read off the contact, because the use_case is about seniority in the room on the day. Organisation distinguishes the client attendees from the partner ones, which the description explicitly separates. Nothing in the register states any of this.

</details>

#### `feature_gaps_logged` — Feature Gaps Logged

Row shape: _inferred_.

| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |
|---|---|---|---|---|---|
| Gap | `gap_description` | long text | **required** | — | declared in extensions.json |
| Suite / Module | `suite_module` | lookup | optional | → `product` | declared in extensions.json |
| Impact | `impact` | picklist | optional | `administration__impact` — Very High · High · Medium · Low | declared in extensions.json |
| Raised By | `raised_by` | lookup | optional | → `user` | declared in extensions.json |

<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>

Derived from the description ('Capability gaps surfaced during the demo') and use_case ('the product feedback loop; each gap is a roadmap candidate'). Gap is free text because the register carries no gap taxonomy. Suite / Module is a products lookup, matching leads.suite_demonstrated one row above it. Impact reuses administration__impact - that picklist is the RISK register's impact scale, borrowed here because no gap-severity set exists; if a gap severity is meant to be its own vocabulary the register must say so. A Roadmap Candidate flag was proposed and REMOVED at review: the use_case already says every gap is a roadmap candidate, so a per-row flag asked the user to re-state something that is true of the whole table. If roadmap TRIAGE needs recording it is a status, not a yes/no - say which values.

</details>

---

## Opportunities

Stages 4–6. Holds `parent_lead`; identity is read through the parent `leads` and rendered read-only.

### HEADER

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Progression % | `progression_pct` | computed | Computed | any | resolved by `progression` — see lib/spec/resolvers.ts<br>0 · 11 · 22 · 33 · 44 · 56 · 67 · 78 · 89 · 100 | NEW |

### RECORD STATE — each module keeps its own instance

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Opportunity Stage | `project_stage` | picklist | **Mandatory** | 0 | **Derived from the module range, not from `leads_stage`** — 4 RFP / RFI · 5 Technical Evaluation · 6 Commercial Evaluation | own instance |
| Opportunity Status | `lead_status` | picklist | **Mandatory** | 0 | `leads__lead_status` — Open · On Hold · Closed Lost · Converted | own instance |
| Probability (%) | `probability_pct` | number | **Mandatory** | 0 | Must sit in the band for the current stage | own instance |

### STAGE 4 — RFP / RFI

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| RFP Type | `rfp_type` | picklist | **Mandatory** | 4 | `leads__rfp_type` — RFP · RFI · Tender · EOI | moved from `leads` |
| RFP Received Date | `rfp_received_date` | date | **Mandatory** | 4 | — | moved from `leads` |
| RFP Document | `rfp_document` | file | **Mandatory** | 4 | — | moved from `leads` |
| Submission Deadline | `submission_deadline` | date-time | **Mandatory** | 4 | — | moved from `leads` |
| ARR (Annual Recurring) | `arr_annual_recurring` | currency | **Mandatory** | 4 | — | moved from `leads` |
| One-Time Revenue | `one_time_revenue` | currency | **Mandatory** | 4 | — | moved from `leads` |
| 3rd-Party One-Time | `3rd_party_one_time` | currency | **Mandatory** | 4 | — | moved from `leads` |
| 3rd-Party Recurring (per year) | `3rd_party_recurring_per_year` | currency | **Mandatory** | 4 | — | moved from `leads` |
| Contract Years | `contract_years` | number | **Mandatory** | 4 | — | moved from `leads` |
| Total Value (TCV) | `total_value_tcv` | computed | Computed | 4 | `arr_annual_recurring * contract_years + perpetual_licence_fee + one_time_revenue + 3rd_party_one_time + 3rd_party_recurring_per_year * contract_years`<br>(ARR × Years) + Perpetual Licence Fee + One-Time + 3rd-Party One-Time + (3rd-Party Recurring × Years) | moved from `leads` |
| Gross Margin % | `gross_margin_pct` | computed | Computed | 4 | `((arr_annual_recurring * contract_years + perpetual_licence_fee + one_time_revenue) - services_and_implementation_cost) / (arr_annual_recurring * contract_years + perpetual_licence_fee + one_time_revenue)`<br>(((ARR × Contract Years) + Perpetual Licence Fee + One-Time Revenue) - Services & Implementation Cost) / ((ARR × Contract Years) + Perpetual Licence Fee + One-Time Revenue). Excludes third-party content. | moved from `leads` |
| Competitors Noticed | `competitors_noticed` | text | **Mandatory** | 4 | max 255<br>Free text. Was typed multiselect with no value set behind it in the register. | moved from `leads` |
| Bid Record | `bid_record` | lookup | **Mandatory** | 4 | → `bid` | moved from `leads` |
| Bid Submission Date | `bid_submission_date` | date-time | **Mandatory** | 4 | — | moved from `leads` |
| Submitted On Time | `submitted_on_time` | computed | Computed | 4 | `bid_submission_date <= submission_deadline`<br>Bid Submission Date ≤ Submission Deadline | moved from `leads` |
| Debrief Requested Date | `debrief_requested_date` | date | Advisory | 4 | — | moved from `leads` |
| Platform Licence List Price | `platform_licence_list_price` | currency | **Mandatory** | 4 | — | moved from `leads` |
| Licence Discount % | `licence_discount_pct` | computed | Computed | 4 | `(platform_licence_list_price - arr_annual_recurring) / platform_licence_list_price`<br>(List Price - ARR) / List Price | moved from `leads` |
| Services & Implementation Cost | `services_and_implementation_cost` | currency | **Mandatory** | 4 | — | moved from `leads` |
| Third-Party Cost | `third_party_cost` | currency | Conditional | 4 | — | moved from `leads` |
| Total Cost | `total_cost` | computed | Computed | 4 | `services_and_implementation_cost + third_party_cost`<br>Services & Implementation Cost + Third-Party Cost | moved from `leads` |
| Third-Party % of TCV | `third_party_pct_of_tcv` | computed | Computed | 4 | `(3rd_party_one_time + 3rd_party_recurring_per_year * contract_years) / total_value_tcv`<br>(3rd-Party One-Time + 3rd-Party Recurring × Years) / Total Value (TCV) | moved from `leads` |
| Cost Model (RCM) Document | `cost_model_rcm_document` | file | **Mandatory** | 4 | — | moved from `leads` |
| Licence Model | `licence_model` | picklist | **Mandatory** | 4 | `leads__licence_model` — Subscription · Perpetual | moved from `leads` |
| Perpetual Licence Fee | `perpetual_licence_fee` | currency | Conditional | 4 | shown when `licence_model == 'Perpetual'` | moved from `leads` |
| Client Tender Reference | `client_tender_reference` | text | Optional | 4 | max 60 | moved from `leads` |
| Primary Quote | `primary_quote` | lookup | **Mandatory** | 4 | → `quote`, filtered: _Status must be Sent_<br>Status must be Sent | moved from `leads` |
| Nomination Bid | `nomination_bid` | checkbox | Optional | 4 | — | NEW |
| Incumbent Only | `incumbent_only` | checkbox | Optional | 4 | — | NEW |
| Parent Lead | `parent_lead` | lookup | System | 4 | → `lead` | NEW |
| Value Confidence | `value_confidence` | picklist | Optional | 4 | `value_confidence` — Budgetary · Firm | NEW |

### STAGE 5 — TECHNICAL EVALUATION

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Bid Receipt Confirmed Date | `bid_receipt_confirmed_date` | date | **Mandatory** | 5 | — | moved from `leads` |
| First TBE Received Date | `first_tbe_received_date` | date | Optional | 5 | — | moved from `leads` |
| Technical Standing | `technical_standing` | picklist | **Mandatory** | 5 | `leads__technical_standing` — Leading · Equal · Trailing · Unknown | moved from `leads` |
| Technical Approval Status | `technical_approval_status` | picklist | **Mandatory** | 5 | `leads__technical_approval_status` — Pending · Approved · On approved vendor list · Rejected | moved from `leads` |
| Technical Approval Date | `technical_approval_date` | date | **Mandatory** | 5 | — | moved from `leads` |

### STAGE 6 — COMMERCIAL EVALUATION

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Commercial Proposal Submitted Date | `commercial_proposal_submitted_date` | date | **Mandatory** | 6 | — | moved from `leads` |
| Final Negotiated Value | `final_negotiated_value` | currency | **Mandatory** | 6 | — | moved from `leads` |
| Contract Review Status | `contract_review_status` | picklist | **Mandatory** | 6 | `leads__contract_review_status` — Not started · In review · Signed off | moved from `leads` |
| Contract Review Sign-Off Date | `contract_review_sign_off_date` | date | **Mandatory** | 6 | — | moved from `leads` |
| Contract Review Sign-Off By | `contract_review_sign_off_by` | lookup | **Mandatory** | 6 | → `user` | moved from `leads` |
| Commercial Gate | `commercial_gate` | lookup | **Mandatory** | 6 | → `gate`<br>Gate Type = Commercial | moved from `leads` |
| Award Type | `award_type` | picklist | **Mandatory** | 6 | `leads__award_type` — LOI · Verbal · PO · Signed contract | moved from `leads` |
| LOI Received Date | `loi_received_date` | date | **Mandatory** | 6 | — | moved from `leads` |
| Agreed Advance % | `agreed_advance_pct` | percent | **Mandatory** | 6 | — | moved from `leads` |
| Agreed Credit Period (days) | `agreed_credit_period_days` | number | **Mandatory** | 6 | — | moved from `leads` |
| Agreed Liability Cap % | `agreed_liability_cap_pct` | percent | **Mandatory** | 6 | — | moved from `leads` |
| Agreed LD Cap % | `agreed_ld_cap_pct` | percent | **Mandatory** | 6 | — | moved from `leads` |
| Pay-When-Paid | `pay_when_paid` | checkbox | Conditional | 6 | shown when `alliance_structure == 'Partner prime'` | moved from `leads` |
| Payment Milestones | `payment_milestones` | child list | **Mandatory** | 6 | row shape in the child-list table below<br>8 standard milestones | moved from `leads` |
| SoW Agreed Date | `sow_agreed_date` | date | **Mandatory** | 6 | — | NEW |
| Bidder Declared Date | `bidder_declared_date` | date | **Mandatory** | 6 | — | NEW |

> 4 further fields in this section — `milestone_—_planned_date`, `milestone_—_actual_date`, `milestone_—_invoice_date`, `milestone_—_payment_received_date` — define row columns of **Payment Milestones** and are listed there, not as record fields.

### __header

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Overall RAG | `overall_rag` | picklist | Optional | any | `overall_rag` — Green · Amber · Red | NEW |
| Next Milestone | `next_milestone` | text | Optional | any | max 200 | NEW |
| Next Milestone Date | `next_milestone_date` | date | Optional | any | — | NEW |
| Pipeline Rank | `pipeline_rank` | number | Optional | any | — | NEW |

### READ THROUGH THE PARENT — resolved from the parent, never stored here

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Opportunity Name | `opportunity_name` | text | **Mandatory** | 0 | max 150<br>Format: [Project Name] — [Client] | read-through from `leads` via `parent_lead` |
| Region | `region` | picklist | **Mandatory** | 0 | `region` — India · MEA · APAC · Americas | read-through from `leads` via `parent_lead` |
| End Client | `end_client` | lookup | **Mandatory** | 0 | → `account`, filtered: _Account Type must include End Client_<br>Account Type must include End Client | read-through from `leads` via `parent_lead` |
| Customer (Partner / SI) | `customer_partner_si` | lookup | **Mandatory** | 0 | → `account`, filtered: _Account Type must include Partner / SI_<br>Account Type must include Partner / SI | read-through from `leads` via `parent_lead` |
| BD Owner | `bd_owner` | lookup | **Mandatory** | 0 | → `user`, filtered: _Role must include BD Owner_<br>Role must include BD Owner | read-through from `leads` via `parent_lead` |
| Primary Contact | `primary_contact` | lookup | Optional | 0 | → `contact` | read-through from `leads` via `parent_lead` |
| Deal Source | `deal_source` | picklist | **Mandatory** | 0 | `leads__deal_source` — Partner-sourced · Direct | read-through from `leads` via `parent_lead` |
| Opportunity Type | `opportunity_type` | picklist | **Mandatory** | 0 | `leads__opportunity_type` — New Logo · Expansion · Renewal | read-through from `leads` via `parent_lead` |
| Partner Deal Registration | `partner_deal_registration` | lookup | Conditional | 0 | → `deal_registration`<br>shown when `deal_source == 'Partner-sourced'` | read-through from `leads` via `parent_lead` |
| Segment | `segment` | picklist | **Mandatory** | 0 | `segment` — Infrastructure · Industry · Power · Mobility | read-through from `leads` via `parent_lead` |
| Theme | `theme` | picklist | **Mandatory** | 0 | `theme` — Smart Cities · Energy Utilities & Critical Infrastructure · Smart Buildings & Campuses · Industry 4.0 & Manufacturing · Data Centers · Defence & Protected Markets · Smart Transport & Infrastructure | read-through from `leads` via `parent_lead` |
| S!aP Solution Suite | `sap_solution_suite` | lookup | **Mandatory** | 0 | → `product`, filtered: _Suite Type must be Primary suite_<br>Suite Type must be Primary suite | read-through from `leads` via `parent_lead` |
| Currency | `currency` | picklist | **Mandatory** | 0 | `leads__currency` — USD · AED · SAR · QAR · OMR · KWD · BHD | read-through from `leads` via `parent_lead` |
| Lighthouse Project | `lighthouse_project` | checkbox | Optional | 0 | — | read-through from `leads` via `parent_lead` |
| Gorilla Flag | `gorilla_flag` | checkbox | Optional | 0 | — | read-through from `leads` via `parent_lead` |
| Suite Demonstrated | `suite_demonstrated` | lookup | **Mandatory** | 1 | → `product` | read-through from `leads` via `parent_lead` |
| Consultant / Specifier | `consultant_specifier` | lookup | **Mandatory** | 3 | → `account` | read-through from `leads` via `parent_lead` |
| Sales Owner | `sales_owner` | lookup | Optional | 3 | → `user`, filtered: _Role must include Sales Owner_<br>Role must include Sales Owner | read-through from `leads` via `parent_lead` |
| Presales Owner | `presales_owner` | lookup | Optional | 3 | → `user`, filtered: _Role must include Presales Owner_<br>Role must include Presales Owner | read-through from `leads` via `parent_lead` |
| Probable Award Date | `probable_award_date` | date | **Mandatory** | 3 | — | read-through from `leads` via `parent_lead` |
| Pre-Bid Alliance Partner | `pre_bid_alliance_partner` | lookup | **Mandatory** | 3 | → `account`<br>shown when `deal_source != 'Direct'` | read-through from `leads` via `parent_lead` |
| Alliance Structure | `alliance_structure` | picklist | **Mandatory** | 3 | `leads__alliance_structure` — Astrikos prime · Partner prime · Consortium / joint bid · Not applicable | read-through from `leads` via `parent_lead` |
| Total Project Value | `total_project_value` | currency | Optional | 3 | shown when `alliance_structure == 'Partner prime'` | read-through from `leads` via `parent_lead` |

### CROSS-CUTTING

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Probability Override Justification | `probability_override_justification` | text | Conditional | any | max 500 | shared from `leads` |
| Stage Skip Reason | `stage_skip_reason` | text | Conditional | any | max 500 | shared from `leads` |
| Stage Reversal Reason | `stage_reversal_reason` | text | Conditional | any | max 500 | shared from `leads` |
| Closed Lost Reason Code | `closed_lost_reason_code` | picklist | Conditional | any | `closed_lost_reason_code` — Lost to competitor · Price · Technical fit · Relationship · Client cancelled · Budget withdrawn · No bid · Partner conflict · Timing<br>shown when `lead_status == 'Closed Lost'` | shared from `leads` |
| On Hold Reason | `on_hold_reason` | text | Conditional | any | max 500<br>shown when `lead_status == 'On Hold'` | shared from `leads` |
| Close Date Pushback Count | `close_date_pushback_count` | computed | Computed | — | **no formula in the register** | shared from `leads` |
| Days in Current Stage | `days_in_current_stage` | computed | Computed | — | **no formula in the register** | shared from `leads` |
| Days Since Last Update | `days_since_last_update` | computed | Computed | — | **no formula in the register** | shared from `leads` |

### SYSTEM

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Created By | `created_by` | lookup | System | — | → `user` | shared from `leads` |
| Created Date | `created_date` | date-time | System | — | — | shared from `leads` |
| Modified By | `modified_by` | lookup | System | — | → `user` | shared from `leads` |
| Modified Date | `modified_date` | date-time | System | — | — | shared from `leads` |

### Opportunities — child lists

Each table below is **one row** of that child list.

#### `payment_milestones` — Payment Milestones

Row shape: _inferred_.

| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |
|---|---|---|---|---|---|
| Milestone | `milestone` | picklist | **required** | `administration__milestone` — Contract signing · Design approval · Submittal approval · FAT · Delivery · Installation · T&C · Handover | declared in extensions.json |
| % of Contract | `pct_of_contract` | percent | **required** | — | declared in extensions.json |
| Trigger | `trigger` | text | optional | max 200 | declared in extensions.json |
| Milestone — Planned Date | `milestone_—_planned_date` | date | **required** | — | register field `opportunities.milestone_—_planned_date` |
| Milestone — Actual Date | `milestone_—_actual_date` | date | optional | — | register field `opportunities.milestone_—_actual_date` |
| Milestone — Invoice Date | `milestone_—_invoice_date` | date | optional | — | register field `opportunities.milestone_—_invoice_date` |
| Milestone — Payment Received Date | `milestone_—_payment_received_date` | date | optional | — | register field `opportunities.milestone_—_payment_received_date` |
| Status | `milestone_status` | picklist | optional | `administration__milestone_status` — Not due · Due · Invoiced · Paid | declared in extensions.json |

<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>

The four milestone_—_* date fields sit flat in STAGE 7 - CLOSE and are the register's only per-milestone columns, so they are read as the row shape and referenced by ref rather than restated - each keeps its own register requirement, which is why Planned Date is demanded and the other three are not. The register's description says 'the eight standard milestones with their percentages and triggers' but the sheet carries no name, percentage or trigger column at all. Milestone therefore reuses administration__milestone, whose eight values (Contract signing, Design approval, Submittal approval, FAT, Delivery, Installation, T&C, Handover) are exactly the eight standard milestones the description means - the earlier note claiming the name column exists nowhere was wrong, it is on the Administration sheet. Status reuses administration__milestone_status. % of Contract and Trigger are new. Note the percent-unit question in conventions applies to % of Contract.

</details>

---

## Deals

Stages 7–9. Holds `parent_opportunity`; identity is read through the parent `opportunities` and rendered read-only.

### HEADER

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Progression % | `progression_pct` | computed | Computed | any | resolved by `progression` — see lib/spec/resolvers.ts<br>0 · 11 · 22 · 33 · 44 · 56 · 67 · 78 · 89 · 100 | NEW |

### RECORD STATE — each module keeps its own instance

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Deal Status | `lead_status` | picklist | **Mandatory** | 0 | `leads__lead_status` — Open · On Hold · Closed Lost · Converted | own instance |
| Probability (%) | `probability_pct` | number | **Mandatory** | 0 | Must sit in the band for the current stage | own instance |

### ON CONVERSION

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Deal ID | `deal_id` | autonumber | System | 7 | DEAL-00001 | — |
| Deal Name | `deal_name` | text | **Mandatory** | 7 | max 150 | — |
| Parent Lead | `parent_lead` | lookup | **Mandatory** | 7 | → `lead` | — |
| End Client | `end_client` | lookup | **Mandatory** | 7 | → `account` | — |
| Customer (Partner / SI) | `customer_partner_si` | lookup | **Mandatory** | 7 | → `account` | — |
| Deal Stage | `deal_stage` | picklist | **Mandatory** | 7 | **Derived from the module range, not from `deals__deal_stage`** — 7 Close · 8 Project Success · 9 Expansion | — |
| Delivery PM | `delivery_pm` | lookup | **Mandatory** | 7 | → `user` | — |
| Order Booked | `order_booked` | checkbox | **Mandatory** | 7 | — | — |
| Booking Date | `booking_date` | date | **Mandatory** | 7 | — | — |
| ERP Reference | `erp_reference` | text | **Mandatory** | 7 | max 50 | — |
| PO / LOI Reference | `po_loi_reference` | text | **Mandatory** | 7 | max 50 | — |
| Project Code | `project_code` | text | **Mandatory** | 7 | max 30 | — |
| Contract Value | `contract_value` | currency | **Mandatory** | 7 | — | — |
| ARR (Annual Recurring) | `arr_annual_recurring` | currency | **Mandatory** | 7 | — | — |
| One-Time Revenue | `one_time_revenue` | currency | **Mandatory** | 7 | — | — |
| 3rd-Party One-Time | `3rd_party_one_time` | currency | **Mandatory** | 7 | — | — |
| 3rd-Party Recurring (per year) | `3rd_party_recurring_per_year` | currency | **Mandatory** | 7 | — | — |
| Contract Years | `contract_years` | number | **Mandatory** | 7 | — | — |
| PSP Completed Date | `psp_completed_date` | date | **Mandatory** | 7 | — | — |
| Handover Pack Delivered Date | `handover_pack_delivered_date` | date | **Mandatory** | 7 | — | — |
| Kickoff Meeting Date | `kickoff_meeting_date` | date | **Mandatory** | 7 | — | — |
| Cash Flow Sign-Off Date | `cash_flow_sign_off_date` | date | **Mandatory** | 7 | — | — |
| Resource Plan Sign-Off Date | `resource_plan_sign_off_date` | date | **Mandatory** | 7 | — | — |
| Bid Commitments Register | `bid_commitments_register` | child list | **Mandatory** | 7 | row shape in the child-list table below | — |
| Parent Opportunity | `parent_opportunity` | lookup | System | 7 | → `opportunity` | NEW |

> 7 further fields in this section — `guarantee_—_type`, `guarantee_—_value`, `guarantee_—_pct_of_contract_value`, `guarantee_—_issue_date`, `guarantee_—_expiry_date`, `guarantee_—_issuing_bank`, `guarantee_—_status` — define row columns of **Bid Commitments Register** and are listed there, not as record fields.

### STAGE 7 — CLOSE

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| PO Number | `po_number` | text | Conditional | 7 | max 50 | moved from `leads` |
| Contract Signed Date | `contract_signed_date` | date | Conditional | 7 | — | moved from `leads` |
| Payment Schedule Confirmed | `payment_schedule_confirmed` | checkbox | **Mandatory** | 7 | — | moved from `leads` |

### STAGE 8 — PROJECT SUCCESS

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Commissioning Date | `commissioning_date` | date | **Mandatory** | 8 | — | — |
| T&C Sign-Off Date | `tandc_sign_off_date` | date | **Mandatory** | 8 | — | — |
| Go-Live Date | `go_live_date` | date | **Mandatory** | 8 | — | — |
| Warranty Start Date | `warranty_start_date` | date | **Mandatory** | 8 | — | — |
| Warranty End Date | `warranty_end_date` | date | **Mandatory** | 8 | — | — |
| Contract Completion Date | `contract_completion_date` | date | **Mandatory** | 8 | — | — |
| CSAT Score | `csat_score` | number | **Mandatory** | 8 | — | — |
| CSAT Date | `csat_date` | date | **Mandatory** | 8 | — | — |
| Reference Status | `reference_status` | picklist | **Mandatory** | 8 | `deals__reference_status` — Secured · In progress · Declined · Not requested | — |
| Reference Document | `reference_document` | file | Optional | 8 | — | — |
| Re-engagement 30-Day Date | `re_engagement_30_day_date` | date | Advisory | 8 | — | — |
| Re-engagement 90-Day Date | `re_engagement_90_day_date` | date | Advisory | 8 | — | — |
| Expansion Use Cases | `expansion_use_cases` | child list | **Mandatory** | 8 | row shape in the child-list table below | — |

### STAGE 9 — EXPANSION & RENEWAL

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Expansion Suites | `expansion_suites` | multi-select | **Mandatory** | 9 | **No value set named in the register** — see Spec Health | — |
| Incremental Value | `incremental_value` | currency | **Mandatory** | 9 | shown when `opportunity_type == 'Expansion'` | — |
| Contract Expiry Date | `contract_expiry_date` | date | **Mandatory** | 9 | — | — |
| Renewal Status | `renewal_status` | picklist | **Mandatory** | 9 | `deals__renewal_status` — Not started · In progress · Signed · Lapsed | — |
| Renewal Signed Date | `renewal_signed_date` | date | Advisory | 9 | — | — |
| Linked Expansion Leads | `linked_expansion_leads` | child list | **Mandatory** | 9 | row shape in the child-list table below | — |

### __header

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Overall RAG | `overall_rag` | picklist | Optional | any | `overall_rag` — Green · Amber · Red | NEW |
| Next Milestone | `next_milestone` | text | Optional | any | max 200 | NEW |
| Next Milestone Date | `next_milestone_date` | date | Optional | any | — | NEW |

### READ THROUGH THE PARENT — resolved from the parent, never stored here

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Opportunity Name | `opportunity_name` | text | **Mandatory** | 0 | max 150<br>Format: [Project Name] — [Client] | read-through from `opportunities` via `parent_opportunity` |
| Region | `region` | picklist | **Mandatory** | 0 | `region` — India · MEA · APAC · Americas | read-through from `opportunities` via `parent_opportunity` |
| BD Owner | `bd_owner` | lookup | **Mandatory** | 0 | → `user`, filtered: _Role must include BD Owner_<br>Role must include BD Owner | read-through from `opportunities` via `parent_opportunity` |
| Primary Contact | `primary_contact` | lookup | Optional | 0 | → `contact` | read-through from `opportunities` via `parent_opportunity` |
| Deal Source | `deal_source` | picklist | **Mandatory** | 0 | `leads__deal_source` — Partner-sourced · Direct | read-through from `opportunities` via `parent_opportunity` |
| Opportunity Type | `opportunity_type` | picklist | **Mandatory** | 0 | `leads__opportunity_type` — New Logo · Expansion · Renewal | read-through from `opportunities` via `parent_opportunity` |
| Partner Deal Registration | `partner_deal_registration` | lookup | Conditional | 0 | → `deal_registration`<br>shown when `deal_source == 'Partner-sourced'` | read-through from `opportunities` via `parent_opportunity` |
| Segment | `segment` | picklist | **Mandatory** | 0 | `segment` — Infrastructure · Industry · Power · Mobility | read-through from `opportunities` via `parent_opportunity` |
| Theme | `theme` | picklist | **Mandatory** | 0 | `theme` — Smart Cities · Energy Utilities & Critical Infrastructure · Smart Buildings & Campuses · Industry 4.0 & Manufacturing · Data Centers · Defence & Protected Markets · Smart Transport & Infrastructure | read-through from `opportunities` via `parent_opportunity` |
| S!aP Solution Suite | `sap_solution_suite` | lookup | **Mandatory** | 0 | → `product`, filtered: _Suite Type must be Primary suite_<br>Suite Type must be Primary suite | read-through from `opportunities` via `parent_opportunity` |
| Currency | `currency` | picklist | **Mandatory** | 0 | `leads__currency` — USD · AED · SAR · QAR · OMR · KWD · BHD | read-through from `opportunities` via `parent_opportunity` |
| Lighthouse Project | `lighthouse_project` | checkbox | Optional | 0 | — | read-through from `opportunities` via `parent_opportunity` |
| Gorilla Flag | `gorilla_flag` | checkbox | Optional | 0 | — | read-through from `opportunities` via `parent_opportunity` |
| Suite Demonstrated | `suite_demonstrated` | lookup | **Mandatory** | 1 | → `product` | read-through from `opportunities` via `parent_opportunity` |
| Consultant / Specifier | `consultant_specifier` | lookup | **Mandatory** | 3 | → `account` | read-through from `opportunities` via `parent_opportunity` |
| Sales Owner | `sales_owner` | lookup | Optional | 3 | → `user`, filtered: _Role must include Sales Owner_<br>Role must include Sales Owner | read-through from `opportunities` via `parent_opportunity` |
| Presales Owner | `presales_owner` | lookup | Optional | 3 | → `user`, filtered: _Role must include Presales Owner_<br>Role must include Presales Owner | read-through from `opportunities` via `parent_opportunity` |
| Probable Award Date | `probable_award_date` | date | **Mandatory** | 3 | — | read-through from `opportunities` via `parent_opportunity` |
| Pre-Bid Alliance Partner | `pre_bid_alliance_partner` | lookup | **Mandatory** | 3 | → `account`<br>shown when `deal_source != 'Direct'` | read-through from `opportunities` via `parent_opportunity` |
| Alliance Structure | `alliance_structure` | picklist | **Mandatory** | 3 | `leads__alliance_structure` — Astrikos prime · Partner prime · Consortium / joint bid · Not applicable | read-through from `opportunities` via `parent_opportunity` |
| Total Project Value | `total_project_value` | currency | Optional | 3 | shown when `alliance_structure == 'Partner prime'` | read-through from `opportunities` via `parent_opportunity` |

### CROSS-CUTTING

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Probability Override Justification | `probability_override_justification` | text | Conditional | any | max 500 | shared from `leads` |
| Stage Skip Reason | `stage_skip_reason` | text | Conditional | any | max 500 | shared from `leads` |
| Stage Reversal Reason | `stage_reversal_reason` | text | Conditional | any | max 500 | shared from `leads` |
| Closed Lost Reason Code | `closed_lost_reason_code` | picklist | Conditional | any | `closed_lost_reason_code` — Lost to competitor · Price · Technical fit · Relationship · Client cancelled · Budget withdrawn · No bid · Partner conflict · Timing<br>shown when `lead_status == 'Closed Lost'` | shared from `leads` |
| On Hold Reason | `on_hold_reason` | text | Conditional | any | max 500<br>shown when `lead_status == 'On Hold'` | shared from `leads` |
| Close Date Pushback Count | `close_date_pushback_count` | computed | Computed | — | **no formula in the register** | shared from `leads` |
| Days in Current Stage | `days_in_current_stage` | computed | Computed | — | **no formula in the register** | shared from `leads` |
| Days Since Last Update | `days_since_last_update` | computed | Computed | — | **no formula in the register** | shared from `leads` |

### SYSTEM

| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |
|---|---|---|---|---|---|---|
| Created By / Date | `created_by_date` | date-time | System | — | — | — |
| Modified By / Date | `modified_by_date` | date-time | System | — | — | — |
| Created By | `created_by` | lookup | System | — | → `user` | shared from `leads` |
| Created Date | `created_date` | date-time | System | — | — | shared from `leads` |
| Modified By | `modified_by` | lookup | System | — | → `user` | shared from `leads` |
| Modified Date | `modified_date` | date-time | System | — | — | shared from `leads` |

### Deals — child lists

Each table below is **one row** of that child list.

#### `bid_commitments_register` — Bid Commitments Register

Row shape: _inferred_.

| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |
|---|---|---|---|---|---|
| Guarantee — Type | `guarantee_—_type` | picklist | optional | `deals__guarantee_type` — ABG Advance · PBG Performance | register field `deals.guarantee_—_type` |
| Guarantee — Value | `guarantee_—_value` | currency | optional | — | register field `deals.guarantee_—_value` |
| Guarantee — % of Contract Value | `guarantee_—_pct_of_contract_value` | computed | optional | `guarantee_—_value / contract_value`<br>Guarantee Value / Contract Value | register field `deals.guarantee_—_pct_of_contract_value` |
| Guarantee — Issue Date | `guarantee_—_issue_date` | date | optional | — | register field `deals.guarantee_—_issue_date` |
| Guarantee — Expiry Date | `guarantee_—_expiry_date` | date | optional | — | register field `deals.guarantee_—_expiry_date` |
| Guarantee — Issuing Bank | `guarantee_—_issuing_bank` | text | optional | max 100 | register field `deals.guarantee_—_issuing_bank` |
| Guarantee — Status | `guarantee_—_status` | picklist | optional | `deals__guarantee_status` — Requested · Issued · Extended · Released · Called | register field `deals.guarantee_—_status` |

<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>

The guarantee_—_* fields sit flat in ON CONVERSION and are read as the row shape, the same pattern as leads.payment_milestones. THE REGISTER CONTRADICTS ITSELF HERE and this shape does not resolve it: the field is described as 'every commitment made during bid and negotiation' with a use_case pointing at TBE responses becoming delivery obligations, but the only per-row columns the sheet carries are bank guarantees. A guarantee is one kind of bid commitment, not all of them - there is no column anywhere for the commitment TEXT, the query it answered, or who owns delivering it. Either the field is misnamed and is really a guarantee register, or a second row shape is missing. Decide before Phase 1.

</details>

#### `expansion_use_cases` — Expansion Use Cases

Row shape: _inferred_.

| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |
|---|---|---|---|---|---|
| No. | `use_case_no` | number | **required** | — | declared in extensions.json |
| Use Case | `use_case_description` | text | **required** | max 255 | declared in extensions.json |
| Status | `use_case_status` | picklist | **required** | `bids_pocs__use_case_status` — Not started · In progress · Demonstrated · Not demonstrated | declared in extensions.json |
| Estimated Value | `estimated_value` | currency | optional | — | declared in extensions.json |

<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>

Mapped onto the POC USE CASE (children) section of the bids_pocs sheet - use_case_no, use_case_description, use_case_status - which is the register's only stated shape for a use case, and onto its bids_pocs__use_case_status picklist. POC use cases and expansion use cases are NOT the same thing: one is evidence during a pilot, the other is a revenue opportunity found during delivery, and Demonstrated / Not demonstrated reads oddly for the second. This is a borrowed shape, not a stated one. Estimated Value is new and has no register column; without it exit criterion X8.3 and deals.incremental_value at Stage 9 have nothing to add up.

</details>

#### `linked_expansion_leads` — Linked Expansion Leads

Row shape: _inferred_ · rows are records of `leads` · read-only.

| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |
|---|---|---|---|---|---|
| Lead ID | `lead_id` | autonumber | optional | LEAD-00001 | register field `leads.lead_id` |
| Opportunity Name | `opportunity_name` | text | optional | max 150<br>Format: [Project Name] — [Client] | register field `leads.opportunity_name` |
| Lead Stage | `project_stage` | picklist | optional | **Derived from the module range, not from `leads_stage`** — 0 Connect · 1 Demo Presentation · 2 POC / Pilot · 3 Prescription | register field `leads.project_stage` |
| Estimated Value | `estimated_value` | currency | optional | — | register field `leads.estimated_value` |

<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>

A linked-record list rather than an editable child - expansion leads are Lead records in their own right, so the rows are displayed and never typed into. The register does not say which lead columns to show; these four are the identifying ones and three of them are also the leading columns of list_views.leads. Estimated Value is used rather than total_value_tcv because a freshly created expansion lead has no financials yet.

</details>

---

## Appendix A — every picklist these modules use

The **key** is what the store holds and what a condition compares against; the **label** is what the screen shows. Inactive options are omitted.

**`accounts__account_target_phase`** — 4 options

| key | label |
|---|---|
| `YEAR_1` | Year 1 |
| `YEAR_2` | Year 2 |
| `YEAR_3` | Year 3 |
| `NOT_TARGETED` | Not targeted |

**`accounts__account_type`** — 5 options

| key | label |
|---|---|
| `END_CLIENT` | End Client |
| `PARTNER_SI` | Partner / SI |
| `CONSULTANT_SPECIFIER` | Consultant / Specifier |
| `OEM_TECHNOLOGY_PARTNER` | OEM / Technology Partner |
| `SECTOR_SPECIALIST` | Sector Specialist |

**`accounts__engagement_cadence`** — 3 options

| key | label |
|---|---|
| `MONTHLY` | Monthly |
| `BI_MONTHLY` | Bi-monthly |
| `DEAL_SPECIFIC_ONLY` | Deal-specific only |

**`accounts__partner_tier`** — 4 options

| key | label |
|---|---|
| `TIER_1_STRATEGIC` | Tier 1 Strategic |
| `TIER_2_COMMERCIAL` | Tier 2 Commercial |
| `REGISTERED` | Registered |
| `NOT_A_PARTNER` | Not a partner |

**`accounts__partner_type`** — 4 options

| key | label |
|---|---|
| `STRATEGIC_MSI` | Strategic MSI |
| `SYSTEMS_INTEGRATOR` | Systems Integrator |
| `OEM_TECHNOLOGY` | OEM / Technology |
| `SECTOR_SPECIALIST` | Sector Specialist |

**`administration__impact`** — 4 options

| key | label |
|---|---|
| `VERY_HIGH` | Very High |
| `HIGH` | High |
| `MEDIUM` | Medium |
| `LOW` | Low |

**`administration__milestone`** — 8 options

| key | label |
|---|---|
| `CONTRACT_SIGNING` | Contract signing |
| `DESIGN_APPROVAL` | Design approval |
| `SUBMITTAL_APPROVAL` | Submittal approval |
| `FAT` | FAT |
| `DELIVERY` | Delivery |
| `INSTALLATION` | Installation |
| `TANDC` | T&C |
| `HANDOVER` | Handover |

**`administration__milestone_status`** — 4 options

| key | label |
|---|---|
| `NOT_DUE` | Not due |
| `DUE` | Due |
| `INVOICED` | Invoiced |
| `PAID` | Paid |

**`bids_pocs__use_case_status`** — 4 options

| key | label |
|---|---|
| `NOT_STARTED` | Not started |
| `IN_PROGRESS` | In progress |
| `DEMONSTRATED` | Demonstrated |
| `NOT_DEMONSTRATED` | Not demonstrated |

**`closed_lost_reason_code`** — 9 options

| key | label |
|---|---|
| `LOST_TO_COMPETITOR` | Lost to competitor |
| `PRICE` | Price |
| `TECHNICAL_FIT` | Technical fit |
| `RELATIONSHIP` | Relationship |
| `CLIENT_CANCELLED` | Client cancelled |
| `BUDGET_WITHDRAWN` | Budget withdrawn |
| `NO_BID` | No bid |
| `PARTNER_CONFLICT` | Partner conflict |
| `TIMING` | Timing |

**`contacts__contact_role`** — 5 options

| key | label |
|---|---|
| `DECM_DECISION_MAKER` | DECM Decision Maker |
| `RECM_RECOMMENDER` | RECM Recommender |
| `INFL_INFLUENCER` | INFL Influencer |
| `INTEL_INTEL_PROVIDER` | INTEL Intel Provider |
| `GENL_GENERAL_CONTACT` | GENL General Contact |

**`contacts__friend_foe_assessment`** — 3 options

| key | label |
|---|---|
| `SUPPORTER` | Supporter |
| `NEUTRAL` | Neutral |
| `BLOCKER` | Blocker |

**`customer_class`** — 3 options

| key | label |
|---|---|
| `A_STRATEGIC_>$2M` | A Strategic (>$2M) |
| `B_COMMERCIAL_$250K_$2M` | B Commercial ($250K-$2M) |
| `C_D_TRANSACTIONAL_<$250K` | C/D Transactional (<$250K) |

**`deals__guarantee_status`** — 5 options

| key | label |
|---|---|
| `REQUESTED` | Requested |
| `ISSUED` | Issued |
| `EXTENDED` | Extended |
| `RELEASED` | Released |
| `CALLED` | Called |

**`deals__guarantee_type`** — 2 options

| key | label |
|---|---|
| `ABG_ADVANCE` | ABG Advance |
| `PBG_PERFORMANCE` | PBG Performance |

**`deals__reference_status`** — 4 options

| key | label |
|---|---|
| `SECURED` | Secured |
| `IN_PROGRESS` | In progress |
| `DECLINED` | Declined |
| `NOT_REQUESTED` | Not requested |

**`deals__renewal_status`** — 4 options

| key | label |
|---|---|
| `NOT_STARTED` | Not started |
| `IN_PROGRESS` | In progress |
| `SIGNED` | Signed |
| `LAPSED` | Lapsed |

**`leads__agreed_next_step`** — 5 options

| key | label |
|---|---|
| `POC_SCOPING` | POC scoping |
| `PRESCRIPTION` | Prescription |
| `RFP` | RFP |
| `IMPLEMENTATION` | Implementation |
| `NONE` | None |

**`leads__alliance_structure`** — 4 options

| key | label |
|---|---|
| `ASTRIKOS_PRIME` | Astrikos prime |
| `PARTNER_PRIME` | Partner prime |
| `CONSORTIUM_JOINT_BID` | Consortium / joint bid |
| `NOT_APPLICABLE` | Not applicable |

**`leads__award_type`** — 4 options

| key | label |
|---|---|
| `LOI` | LOI |
| `VERBAL` | Verbal |
| `PO` | PO |
| `SIGNED_CONTRACT` | Signed contract |

**`leads__client_phase`** — 3 options

| key | label |
|---|---|
| `SOLUTION_DESIGN` | Solution design |
| `BUDGETING` | Budgeting |
| `NEITHER` | Neither |

**`leads__contract_review_status`** — 3 options

| key | label |
|---|---|
| `NOT_STARTED` | Not started |
| `IN_REVIEW` | In review |
| `SIGNED_OFF` | Signed off |

**`leads__ctb_approval_status`** — 6 options

| key | label |
|---|---|
| `NOT_STARTED` | Not started |
| `IN_PROGRESS` | In progress |
| `APPROVED` | Approved |
| `APPROVED_WITH_CONDITIONS` | Approved with conditions |
| `DEFERRED` | Deferred |
| `NO_BID` | No bid |

**`leads__currency`** — 7 options

| key | label |
|---|---|
| `USD` | USD |
| `AED` | AED |
| `SAR` | SAR |
| `QAR` | QAR |
| `OMR` | OMR |
| `KWD` | KWD |
| `BHD` | BHD |

**`leads__deal_source`** — 2 options

| key | label |
|---|---|
| `PARTNER_SOURCED` | Partner-sourced |
| `DIRECT` | Direct |

**`leads__interest_level`** — 3 options

| key | label |
|---|---|
| `HIGH` | High |
| `MEDIUM` | Medium |
| `LOW` | Low |

**`leads__lead_status`** — 4 options

| key | label |
|---|---|
| `OPEN` | Open |
| `ON_HOLD` | On Hold |
| `CLOSED_LOST` | Closed Lost |
| `CONVERTED` | Converted |

**`leads__licence_model`** — 2 options

| key | label |
|---|---|
| `SUBSCRIPTION` | Subscription |
| `PERPETUAL` | Perpetual |

**`leads__opportunity_type`** — 3 options

| key | label |
|---|---|
| `NEW_LOGO` | New Logo |
| `EXPANSION` | Expansion |
| `RENEWAL` | Renewal |

**`leads__pilot_commercial_model`** — 2 options

| key | label |
|---|---|
| `FREE` | Free |
| `PAID` | Paid |

**`leads__rfp_type`** — 4 options

| key | label |
|---|---|
| `RFP` | RFP |
| `RFI` | RFI |
| `TENDER` | Tender |
| `EOI` | EOI |

**`leads__technical_approval_status`** — 4 options

| key | label |
|---|---|
| `PENDING` | Pending |
| `APPROVED` | Approved |
| `ON_APPROVED_VENDOR_LIST` | On approved vendor list |
| `REJECTED` | Rejected |

**`leads__technical_standing`** — 4 options

| key | label |
|---|---|
| `LEADING` | Leading |
| `EQUAL` | Equal |
| `TRAILING` | Trailing |
| `UNKNOWN` | Unknown |

**`overall_rag`** — 3 options

| key | label |
|---|---|
| `GREEN` | Green |
| `AMBER` | Amber |
| `RED` | Red |

**`partners__decision`** — 3 options

| key | label |
|---|---|
| `AWARDED_TO_REGISTRATION_A` | Awarded to Registration A |
| `AWARDED_TO_REGISTRATION_B` | Awarded to Registration B |
| `BOTH_DECLINED` | Both declined |

**`partners__partner_role`** — 2 options

| key | label |
|---|---|
| `PRIME` | Prime |
| `SUB` | Sub |

**`partners__quarter`** — 4 options

| key | label |
|---|---|
| `Q1` | Q1 |
| `Q2` | Q2 |
| `Q3` | Q3 |
| `Q4_PLUS_YEAR` | Q4 plus year |

**`partners__registration_status`** — 7 options

| key | label |
|---|---|
| `SUBMITTED` | Submitted |
| `ACKNOWLEDGED` | Acknowledged |
| `ACTIVE` | Active |
| `EXTENDED` | Extended |
| `EXPIRED` | Expired |
| `SUPERSEDED` | Superseded |
| `REJECTED` | Rejected |

**`region`** — 4 options

| key | label |
|---|---|
| `INDIA` | India |
| `MEA` | MEA |
| `APAC` | APAC |
| `AMERICAS` | Americas |

**`segment`** — 4 options

| key | label |
|---|---|
| `INFRASTRUCTURE` | Infrastructure |
| `INDUSTRY` | Industry |
| `POWER` | Power |
| `MOBILITY` | Mobility |

**`theme`** — 7 options

| key | label |
|---|---|
| `SMART_CITIES` | Smart Cities |
| `ENERGY_UTILITIES_CRITICAL_INFRASTRUCTURE` | Energy Utilities & Critical Infrastructure |
| `SMART_BUILDINGS_CAMPUSES` | Smart Buildings & Campuses |
| `INDUSTRY_4_0_MANUFACTURING` | Industry 4.0 & Manufacturing |
| `DATA_CENTERS` | Data Centers |
| `DEFENCE_PROTECTED_MARKETS` | Defence & Protected Markets |
| `SMART_TRANSPORT_INFRASTRUCTURE` | Smart Transport & Infrastructure |

**`value_confidence`** — 2 options

| key | label |
|---|---|
| `BUDGETARY` | Budgetary |
| `FIRM` | Firm |

---

## Appendix B — what the split did, and what it did not

The three-module pipeline agreed at the 14-stage review is applied to the **spec layer**. The screens still show the old two-module shape — Lead detail rails 0–7 and Deal detail rails 8–9 — until they are rebuilt around the split. Conversions, the readiness panel and the store are later steps.

### Fields the register does not carry

Declared in `spec/extensions.json` `new_fields`, so `spec/fields.json` stays generated. 10 gap-fix fields and 2 structural links — the parent lookups carry-forward-by-reference runs on, counted apart because plumbing is not an invented requirement.

| Field | api_name | Type | Module | Stage | Kind |
|---|---|---|---|---|---|
| Progression % | `progression_pct` | computed | `leads` | header | gap fix |
| Progression % | `progression_pct` | computed | `opportunities` | header | gap fix |
| Progression % | `progression_pct` | computed | `deals` | header | gap fix |
| Nomination Bid | `nomination_bid` | checkbox | `opportunities` | 4 | gap fix |
| Incumbent Only | `incumbent_only` | checkbox | `opportunities` | 4 | gap fix |
| SoW Agreed Date | `sow_agreed_date` | date | `opportunities` | 6 | gap fix |
| Bidder Declared Date | `bidder_declared_date` | date | `opportunities` | 6 | gap fix |
| Parent Lead | `parent_lead` | lookup | `opportunities` | 4 | structural link |
| Parent Opportunity | `parent_opportunity` | lookup | `deals` | 7 | structural link |
| Value Confidence | `value_confidence` | picklist | `opportunities` | 4 | gap fix |
| Overall RAG | `overall_rag` | picklist | `leads` | header | gap fix |
| Next Milestone | `next_milestone` | text | `leads` | header | gap fix |
| Next Milestone Date | `next_milestone_date` | date | `leads` | header | gap fix |
| Overall RAG | `overall_rag` | picklist | `opportunities` | header | gap fix |
| Next Milestone | `next_milestone` | text | `opportunities` | header | gap fix |
| Next Milestone Date | `next_milestone_date` | date | `opportunities` | header | gap fix |
| Overall RAG | `overall_rag` | picklist | `deals` | header | gap fix |
| Next Milestone | `next_milestone` | text | `deals` | header | gap fix |
| Next Milestone Date | `next_milestone_date` | date | `deals` | header | gap fix |
| Pipeline Rank | `pipeline_rank` | number | `opportunities` | header | gap fix |

### Identity is carried by reference

An Opportunity holds `parent_lead`; a Deal holds `parent_opportunity`. The 23 identity fields below are **read through that link and rendered read-only** — never copied, so the same value cannot drift in two places. They appear in `fieldsOf(module)` because a criterion or a formula naming a parent field would otherwise stop compiling; carrying them made one previously-broken expression compile again (`deals.incremental_value`, whose visibility rule reads `opportunity_type`).

`opportunity_name` · `end_client` · `customer_partner_si` · `pre_bid_alliance_partner` · `primary_contact` · `partner_deal_registration` · `segment` · `theme` · `sap_solution_suite` · `suite_demonstrated` · `currency` · `total_project_value` · `probable_award_date` · `deal_source` · `opportunity_type` · `alliance_structure` · `bd_owner` · `sales_owner` · `presales_owner` · `consultant_specifier` · `region` · `lighthouse_project` · `gorilla_flag`

Deals takes 18 of the 20: the Deals sheet declares `end_client` and `customer_partner_si` itself. Whether those two register rows should be read-through instead is an open question on Spec Health, not something the loader decided.

### Register corrections this raises

Stage options are derived from the module range plus `spec/stages.json`, never from a picklist. No picklist was patched in a sidecar to make the split work, so each of these stays visible until the workbook is regenerated.

- **`spec/stages.json`** — applies_to still says stages 4, 5, 6 and 7 are 'lead'. Under the split, 4-6 belong to Opportunities and 7 to Deals. Nothing reads applies_to any more - spec/module_split.json ranges are the authority - but the workbook should be regenerated so the two agree.
- **`spec/picklists.json leads_stage`** — Still carries 4_RFP_RFI, 5_TECHNICAL_EVAL, 6_COMMERCIAL_EVAL and 7_CLOSE. A Lead now stops at Stage 3, so four of its eight keys are unreachable from the Leads module. Stage options are derived from the module range instead of this picklist; regenerate it from the split.
- **`spec/picklists.json deals__deal_stage`** — Carries 8_PROJECT_SUCCESS, 9_EXPANSION and CLOSED. A Deal now OPENS at Stage 7 and there is no 7_CLOSE key to store. Stage options are derived from the module range instead. Separately, CLOSED is a status, not a stage, and does not belong in a stage picklist.
- **`deals.created_by_date`** — The Deals sheet names the record's creation timestamp created_by_date and its modification timestamp modified_by_date, where every other sheet uses created_date / modified_date plus a separate created_by lookup. The shared SYSTEM section therefore lands a near-duplicate pair on Deals. Declared in shared.equivalence above; rename in the workbook rather than in a sidecar.

### Refs still written the old way

13 sidecar refs name a module their field has left. Every one still resolves — the loader keeps a `movedRefs` fall-through, so the split needed no hand-editing of `extensions.json` — and every one is listed on Spec Health rather than silently rewritten.

| Written as | Now lives at | Where |
|---|---|---|
| `leads.total_value_tcv` | `opportunities.total_value_tcv` | extensions.json fields |
| `leads.gross_margin_pct` | `opportunities.gross_margin_pct` | extensions.json fields |
| `leads.submitted_on_time` | `opportunities.submitted_on_time` | extensions.json fields |
| `leads.licence_discount_pct` | `opportunities.licence_discount_pct` | extensions.json fields |
| `leads.total_cost` | `opportunities.total_cost` | extensions.json fields |
| `leads.third_party_pct_of_tcv` | `opportunities.third_party_pct_of_tcv` | extensions.json fields |
| `leads.primary_quote` | `opportunities.primary_quote` | extensions.json fields |
| `leads.payment_milestones` | `opportunities.payment_milestones` | extensions.json fields |
| `leads.total_value_tcv` | `opportunities.total_value_tcv` | extensions.json list_views.leads |
| `leads.milestone_—_planned_date` | `opportunities.milestone_—_planned_date` | child_spec of opportunities.payment_milestones |
| `leads.milestone_—_actual_date` | `opportunities.milestone_—_actual_date` | child_spec of opportunities.payment_milestones |
| `leads.milestone_—_invoice_date` | `opportunities.milestone_—_invoice_date` | child_spec of opportunities.payment_milestones |
| `leads.milestone_—_payment_received_date` | `opportunities.milestone_—_payment_received_date` | child_spec of opportunities.payment_milestones |

### Not settled

- **Nomination Bid and Incumbent Only adjust probability, but `spec/stages.json` carries no uplift for either.** Every stage row holds only `prob_min`, `prob_max`, `owner_role`, `bid_phase` and `applies_to`. The boxes record the fact and probability is untouched; no number is invented. Incumbent advantage is written in the playbook as a *range*, which a single uplift field cannot hold.
- **Progression % is linear by stage position** — position in the ordered 0–9 list ÷ (count − 1), read from `stages.json` and never hardcoded to 9. The register states no progression curve. It is shown BESIDE Probability, never instead of it: at Stage 7 they read 78% and 90–100%, and that difference is the point.

