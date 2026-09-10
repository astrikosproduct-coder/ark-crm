# backend/ — the database-backed modules

FastAPI + SQLAlchemy + psycopg over PostgreSQL 17. Round 1 migrated three
modules off the mock store: **users/roles**, **accounts** and **contacts**.

## Users and roles

Owns `users`, `roles` and `user_roles`, served to two audiences:

* `/api/admin/*` — the Administration module's own CRUD, with nested role objects.
* `/api/users` — the **user directory**, read by all 27 user-lookup fields across
  the application (`bd_owner`, `account_owner`, `engagement_owner`, …). Shaped to
  match what `spec/seed/users.json` used to provide, so no lookup field changed.

Every OTHER module is still browser-only and answered by MSW from
`frontend/spec/*.json` — see hard rule 1 in the repo-root `CLAUDE.md`.

This folder was previously a deliberate placeholder. That rule was revisited and
changed on purpose; it was not worked around.

## Layout

```
app/
  database.py       engine, SessionLocal, Base, get_db   (DATABASE_URL from .env)
  models.py         business tables, then the ROUND 6 metadata tables
  schemas.py        Pydantic request/response models for business records
  schemas_metadata.py  …and for the metadata layer, kept separate
  metadata_spec.py  register shape, snapshots, validation, JSON generation
  routers/
    admin.py      Administration CRUD, mounted at /api/admin
    metadata.py   the field register as data, at /api/admin/metadata
    directory.py  the user directory, mounted at /api
    accounts.py   accounts + the list contract, mounted at /api
    contacts.py   contacts, mounted at /api
  main.py         app, CORS, create_all, router mounts
alembic/                migration history (Round 6 onward)
seed.py                 idempotent: system roles + the user directory
reconcile_user_ids.py   one-off: freed USR-001..006 for the directory
migrate_accounts.py     one-off: seed/accounts.json -> PostgreSQL
migrate_contacts.py     one-off: seed/contacts.json -> PostgreSQL
bootstrap_metadata.py   one-off: spec/*.json -> the metadata tables
regenerate_spec.py      ongoing: the metadata tables -> spec/*.json
test_metadata_round6.py end-to-end rehearsal of the Round-6 lifecycle
```

## Migrations

Round 6 introduced **Alembic**. Schema changes go through a migration from here
on; `Base.metadata.create_all` still runs at startup, but only as a convenience
that creates anything missing on a fresh local database. It is not how the schema
evolves, and it is a no-op once migrations have brought a database up to date.

```bash
./.venv/Scripts/python.exe -m alembic upgrade head        # apply
./.venv/Scripts/python.exe -m alembic revision --autogenerate -m "what changed"
./.venv/Scripts/python.exe -m alembic check               # any model drift?
```

| Revision | What |
|---|---|
| `0001_baseline` | The schema as Rounds 1–5 left it. A record of the starting point |
| `0002_round6` | The seven metadata tables |
| `0003_picklist_sort` | `picklists.sort_order`, so regenerating does not reshuffle the file |
| `0004_custom_fields` | `custom_fields` JSONB on the five business tables; `field_metadata.storage` |
| `0005_opportunities` | Opportunities as a module row; pipeline structure into `modules`/`stages` |
| `0006_cf_gin` | GIN (`jsonb_path_ops`) indexes on every `custom_fields` column |
| `0007_capture_stage` | Backfills `capture_stage` on pipeline fields in numbered STAGE sections |

**On a database that already has the Rounds 1–5 tables** (created by `create_all`
before Alembic existed), stamp the baseline rather than running it — the tables
are already there and `0001` would fail on its first `CREATE TABLE`:

```bash
./.venv/Scripts/python.exe -m alembic stamp 0001_baseline
./.venv/Scripts/python.exe -m alembic upgrade head
```

On an empty database, `alembic upgrade head` builds everything.

`alembic check` reports two tables the models no longer declare —
`lead_secondary_suites` and `deal_expansion_suites`, left behind by the Phase-1
freeze of those two multiselects to free text. They are deliberately not dropped:
an untouched leftover beats a migration that destroys data to tidy up.

## Running

Postgres runs in Docker (`ark-postgres`, host port **5433**). Then:

```bash
cd backend
./.venv/Scripts/python.exe -m alembic upgrade head   # schema
./.venv/Scripts/python.exe seed.py                   # idempotent: roles + users
./.venv/Scripts/python.exe migrate_accounts.py       # dry run; --apply to write
./.venv/Scripts/python.exe bootstrap_metadata.py     # dry run; --apply to write
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Interactive docs: <http://localhost:8000/docs>

### Endpoints

All under `/api/admin`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/roles` | The 9 seeded system roles |
| GET | `/users` | Every user with roles; `?q=` filters on **name** |
| GET | `/users/next-id` | Suggested next `USR-00N` (a suggestion, not a sequence) |
| GET | `/users/{user_id}` | One user |
| POST | `/users` | Create, optionally with `role_ids` |
| PATCH | `/users/{user_id}` | Partial update of name / email / active |
| PATCH | `/users/{user_id}/active` | Activate or deactivate |
| GET | `/users/{user_id}/roles` | That user's roles |
| PUT | `/users/{user_id}/roles` | **Replace** the whole role set; `[]` clears it |

Plus the directory, at `/api`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/users` | Every user, in the legacy mock shape (`id`, flat `roles`) |
| GET | `/users/{user_id}` | One user, same shape |

Both prefixes sit under `/api` so the frontend keeps using its single Axios
client (`baseURL: '/api'`). MSW passes `/api/admin/*`, `/api/users` and
`/api/users/*` through, and Vite's dev proxy forwards them here, so the browser
stays same-origin. **Adding a new passed-through path needs both** — an MSW
handler above the catch-alls *and* a `server.proxy` entry in `vite.config.ts`.

### Design notes

- **`user_id` is the primary key**, a VARCHAR holding the workbook's `USR-001`
  reference style. `user_roles` rows stay readable in psql as a result. The admin
  types the id; the API only suggests the next one.
- **Roles are a junction table**, never a string, array or JSONB column — the
  register calls Roles a multi-select, and this is what a multi-select is
  relationally.
- **`role_id` holds the picklist key** from `spec/picklists.json`
  (`administration__roles`): `BD_OWNER`, `APPROVER`, and so on. One vocabulary
  shared by the database and the field register.
- **Roles are system-defined.** They are seeded and read-only over the API; there
  is deliberately no role-creation or permission-management endpoint yet.
- **Deactivation is not deletion.** A deactivated user keeps their roles and
  history, and `/api/users` still returns them — an owner already named on a
  lead must not vanish from that record. *Who may be picked* is a spec concern
  (`lookup_filter_expr`), not a transport concern.
- **`USR-001` to `USR-006` are pinned.** Records across `spec/seed/*.json`
  reference them 42 times as owners. `seed.py`'s `DIRECTORY_USERS` holds those
  exact ids; changing one silently repoints or blanks an owner on existing demo
  records. The initial admin was moved to `USR-900` to free `USR-001`.
- **The seed never overwrites a person.** Roles are configuration and are kept in
  step with the spec on every run; users are data, so once someone exists their
  name, email and roles are left alone — an admin may have edited them in the UI.

## Accounts

An **Account is an organisation**. End Clients and Partners are both accounts —
there is no separate partners table, and the Partners screen is a *view* over
this collection filtered by `account_type`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/accounts` | List, with the full query contract below |
| GET | `/api/accounts/{account_id}` | One account |
| POST | `/api/accounts` | Create; the server allocates the next `ACC-nnn` |
| PATCH | `/api/accounts/{account_id}` | Apply the fields sent |
| PUT | `/api/accounts/{account_id}` | Same; kept because the record editor and `LeadAccountFieldSync` both PUT |
| DELETE | `/api/accounts/{account_id}` | Real delete — the register gives an account no `active` flag |

### The list contract

`GET /accounts` reproduces what `src/mocks/query.ts` does for mocked
collections, because the frontend's list component cannot tell the two apart:

* any non-reserved parameter is an equality filter; **repeating it is an OR**,
  which is how Partners asks for two account types at once
* `q` searches `account_name`, `region`, `segment` (or the `_search` list)
* `_sort` / `_order`, `_page` / `_limit`, and the total on `X-Total-Count`
* `__labels` carries the resolved `account_owner` name, joined server-side so a
  page of 25 rows is one request rather than twenty-six

### The 18 register fields

Seventeen are columns. The one **multiselect gets a junction table** — the same
rule `user_roles` follows, never a delimited string, an array column or JSONB:

* `account_types` — `account_type` holds a key from `accounts__account_type`

`account_owner` is a real **foreign key to `users.user_id`**; an unknown id is
rejected with a 422 naming the field.

Picklist columns store the **key** from `spec/picklists.json`
(`INFRASTRUCTURE`, not `Infrastructure`). That file stays the single vocabulary;
the database does not duplicate it, and `migrate_accounts.py` reproduces the
frontend's label→key normalisation so the two agree.

### Known gaps

* **Platform Depth was deleted, 01 Sep 2026.** It existed twice in the register
  (accounts / PARTNER ATTRIBUTES and partners / QUARTERLY SCORECARD) and named
  no picklist in either place, so the control could never hold a value. Both
  rows were removed from `spec/fields.json` and the `account_platform_depth`
  table was dropped. **`spec/fields.json` is generated — the row must also be
  deleted from the workbook**, or the next regeneration reinstates it. Recorded
  under `extensions.json` `open_questions`, ref `accounts.platform_depth`.
* **Sorting picklist columns orders by key, not label.** The keys are
  upper-cased forms of the same words, so the order matches for every current
  picklist; a label that diverged from its key would need the vocabulary
  server-side.
* **`Mandatory` is not `NOT NULL`.** Only `account_name` is NOT NULL. Mandatory
  in the register is a stage-gating rule the form engine enforces — a
  half-filled account must still save, or the prototype cannot show the gap.

## Contacts

A **Contact is an external person at an Account**. Users are internal ARK
employees and live in `users`; the two are never mixed — a contact has no login
and holds no role, and `engagement_owner` is a *user*, not another contact.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/contacts` | List, same query contract as accounts |
| GET | `/api/contacts/{contact_id}` | One contact |
| POST | `/api/contacts` | Create; the server allocates the next `CON-nnn` |
| PATCH | `/api/contacts/{contact_id}` | Apply the fields sent |
| PUT | `/api/contacts/{contact_id}` | Same; the record editor PUTs when it saves |
| DELETE | `/api/contacts/{contact_id}` | Real delete — the register gives a contact no `active` flag |

### The 15 register fields

All scalar. Contacts carries **no multiselect**, so unlike accounts it needs no
junction table. Two real foreign keys:

* `account` → `accounts.account_id`
* `engagement_owner` → `users.user_id`

Both are **ON DELETE SET NULL**, not CASCADE: deleting an organisation or an
employee must not silently delete the people recorded against them. The contact
survives with the link cleared, which is visible on screen and recoverable.

Columns are named after their register api_name, so the column is `account`
rather than `account_id` — the same rule `accounts.account_owner` follows. The
relationship is identical; matching the api_name means no translation layer
between the database and the form engine.

### Search and sort resolve lookups

`extensions.json` asks Contacts to search on `account`, which is a lookup. So
`q` and `_sort` run against the **displayed label** ("Khazna Data Centers"),
not the stored `ACC-001` — searching for an id nobody can see would be useless.
Accounts sorts picklists by key; Contacts sorts lookups by label.

### Note on the seed migration

`migrate_contacts.py` needed one rule `migrate_accounts.py` did not. The seed
stores `contact_role` as `"DECM"` while the picklist key is
`DECM_DECISION_MAKER`. `resolvePicklistValue` has a third fallback matching a
value against the **leading code** of a key, and the migration reproduces it —
without it every contact would land with an unresolved role and a blank badge.


## Retiring a record: deactivate vs delete

Accounts and Contacts both carry an **`active`** flag and the same rule:

> **Hard delete only when nothing depends on the record. Otherwise it is blocked
> and deactivation is the only option.**

`PATCH /api/accounts/{id}/active` and `PATCH /api/contacts/{id}/active` take
`{"active": bool}`, mirroring the users endpoint.

`DELETE /api/accounts/{id}` returns **409** naming the dependants when contacts
still point at it. That is the guard the *database* can enforce, because
`contacts.account` is a real foreign key. Leads, deals, quotes and registrations
still live in the mock store, so the frontend checks those before it ever calls
DELETE — see `src/components/record/DeleteRecordDialog.tsx`.

Nothing in the database holds a foreign key to a contact, so
`DELETE /api/contacts/{id}` has no server-side guard; its dependants
(`leads.primary_contact`, `quotes.sent_to`, the bid signatories) are all mock
records and are checked in the browser.

### `active` is a system lifecycle field

`accounts.active` and `contacts.active` are real `NOT NULL BOOLEAN DEFAULT true`
columns. Neither sheet has the field in the workbook yet — both are recorded as
**ACTION REQUIRED** spec updates in `extensions.json` `open_questions`
(refs `accounts.active`, `contacts.active`), asking for `Active` to be added as
checkbox / System / default true.

They are deliberately **not** rendered as normal form fields — the flag is set
only by the Deactivate action on the record screen. (`spec/fields.json` is
generated, so a hand-added row would be overwritten anyway.)

What deactivating does:

* the record **stays** in the database and in every historical list view
* it keeps resolving its name wherever it is **already** referenced
* it is **excluded from lookup and dropdown options** for new records
  (`LookupCombobox`), with one exception: the value a record already holds stays
  visible in its own control, so opening an old record never silently blanks a
  field

### Reference ids are never reused

`ACC-020`, `CON-016` and friends come from a stored high-water mark in the
**`id_sequences`** table, not from `max(existing) + 1`.

That was a real bug, not a theoretical one. Deriving the next id from the
maximum hands the same id back the moment the newest row is deleted, and the new
record then inherits every stale reference to the old one — a reviewer created
an account, opened it, and found it already "referenced" by leads it had never
met. A stored counter cannot be lowered by a DELETE. See `app/ids.py`.

### References are listed, never counted

The first version of the delete dialog asked the list endpoint
`?end_client=ACC-019&_limit=1` per field and summed `X-Total-Count`. A filter is
a string comparison, so an empty or unexpected id matched every row whose field
was merely blank — `String(value ?? '')` equals `''` — and a reviewer was shown
*"7 records still reference this account"* for an account created seconds
earlier. Nothing is inferred from a count any more: the rows are fetched and the
value compared field by field, and the dialog names each hit
(`LEAD-00123 · Cognus DR Site — End Client`) so it can be clicked and checked.

## Round 6 — the metadata layer

Seven tables that hold **the field register itself** as data: `modules`,
`sections`, `field_metadata`, `picklists`, `picklist_values`, `stages` and
`metadata_versions`. They define what a business record may contain; they never
hold business data.

### The direction of truth

```
Administration UI → PostgreSQL → publish → regenerate → spec/*.json → frontend
```

**PostgreSQL is the source of truth for editable metadata.** The three generated
files — `fields.json`, `picklists.json`, `stages.json` — are a Phase-1
compatibility layer, kept because the frontend already imports them at build
time. They are build artefacts.

| Direction | Supported |
|---|---|
| PostgreSQL → generated JSON | **Yes.** The only supported direction |
| JSON → PostgreSQL | **No.** `bootstrap_metadata.py` crossed that line once and refuses to do it again |

A hand-edit of a generated spec file changes nothing in the database, is not an
Administration update, and is overwritten by the next publish.

`extensions.json` is **not** part of this. It is hand-maintained, it is not
regenerated, and `field_metadata.extension` only mirrors it read-only so the
Administration screen can warn that a field has a computed expression or
child-list shape behind it.

### Field deletion is logical, always

```
Admin deletes → field_metadata.status = 'deleted' → gone from the CRM at the
next publish → business column untouched → values untouched → restorable
```

Administration **never** issues `DROP COLUMN` and never deletes a stored value.
If a business column ever genuinely has to go, that is a reviewed migration of
its own, not a click in an admin screen.

`requirement` is an application rule — the red asterisk and layer 1 of the
transition check. It is deliberately **not** propagated to the column's
nullability: marking a field required must not make an existing half-filled
record unsavable.

### Two different recoveries, kept apart

| | What it moves |
|---|---|
| **Restore a deleted field** | That one field, with its previous configuration. Nothing else |
| **Roll back a version** | The entire configuration, back to an earlier published snapshot |

Rollback **extends** history rather than rewinding it: republishing version 2
creates version 4 carrying version 2's snapshot, with `restored_from = 2`.
Published versions are immutable. Nothing is destroyed on the way — a field the
old snapshot does not carry is logically deleted, so rolling forward brings it
back.

### Draft → review → publish

Edits land in the six tables immediately and change nothing a user sees. Publish
validates, freezes an immutable snapshot, and regenerates the spec files. A draft
that does not validate never becomes a published version and never reaches disk.

Validation separates **errors** (broken configuration — publish refuses) from
**warnings** (register gaps — publish proceeds and says so). The register ships
with 74 warnings today: Conditional fields that state no condition, picklist
fields that name no picklist. Refusing to publish until the register is perfect
would mean never publishing again.

### Commands

```bash
./.venv/Scripts/python.exe bootstrap_metadata.py --apply   # once, ever
./.venv/Scripts/python.exe regenerate_spec.py --check      # DB vs disk
./.venv/Scripts/python.exe regenerate_spec.py --apply      # write the files
./.venv/Scripts/python.exe regenerate_spec.py --version 3 --apply
./.venv/Scripts/python.exe test_metadata_round6.py         # 22 end-to-end checks
```

`--check` compares **meaning, not bytes**: three of the register's 566 rows carry
their 24 keys in a different order to the other 563, so a byte comparison would
report a difference forever and teach everyone to ignore it.

### Endpoints

All under `/api/admin/metadata`. Mounted there on purpose — MSW's existing
`/api/admin/*` passthrough and Vite's `/api/admin` proxy already match it, so
Round 6 needed no new entry in either.

| Method | Path | Purpose |
|---|---|---|
| GET | `/modules`, `/sections`, `/fields`, `/picklists`, `/stages` | Read the draft |
| POST/PATCH | the same, plus `/picklist-values` | Edit the draft |
| PATCH | `/fields/{id}/required` | The Required toggle. Form rule only |
| DELETE | `/fields/{id}` | **Logical** delete |
| POST | `/fields/{id}/restore` | Bring it back |
| POST | `/{thing}/reorder` | Whole-list reorder |
| GET | `/draft` | What is pending, in words, plus validation |
| GET | `/validate` | Would it publish? |
| POST | `/publish` | Freeze a version and regenerate the JSON |
| GET | `/versions`, `/versions/{n}` | Immutable history |
| POST | `/versions/{n}/rollback` | Republish an earlier snapshot as a new version |

`api_name`, `module_key`, a picklist value's `key` and a stage's number are all
**not editable**. Each is a key that stored data is written under, so renaming
one would orphan every existing value while appearing to work. Labels are
editable; retiring something is deactivation or logical deletion.


## Round-6 gap closure

Four gaps the Round-6 audit left open, closed before Round 7 removes MSW.

### Opportunities is a real module

The register has no `opportunities` sheet — it files every Stage 0-7 pipeline
field under `leads`, and the frontend splits them at load time. PostgreSQL
therefore knew nothing about Opportunities, and the backend's only knowledge was
a hardcoded tuple saying "opportunities may also take fields from leads".

Now in the database, on the existing generic tables:

| Where | What |
|---|---|
| `modules.opportunities` | a real module row, active, ordered after Leads |
| `modules.is_pipeline` | Leads, Opportunities and Deals |
| `modules.stage_field` | `project_stage` / `project_stage` / `deal_stage` |
| `modules.parent_module` / `parent_link` | opps → leads via `parent_lead`; deals → opps via `parent_opportunity` |
| `stages.owner_module` | 0-3 leads, 4-6 opportunities, 7-9 deals |

`app/module_split.py` answers the structural questions from those rows, and
`custom_fields.py` uses it instead of the hardcoded map. `ranges` is DERIVED
from stage ownership rather than stored beside it, so the two cannot disagree.

**spec/module_split.json is now part generated.** `pipeline`, `ranges`,
`stage_field`, `reassign` and `read_through.parent_of` / `parent_link` are
rewritten from PostgreSQL on every publish. Its per-field judgement calls —
`own`, `read_through.fields`, `shared`, `section_order`, `relocated_fields`,
`register_corrections` — have no database representation and are preserved
byte-for-byte, on the same footing as `extensions.json`.

**No Opportunity field rows were materialised.** Every Opportunity field is a
projection of a Leads register row; storing them would be the duplicate metadata
this round was told not to create, and it would drift from the frontend's
derivation. The projection stays in `src/lib/spec/moduleSplit.ts` and now reads
its inputs from PostgreSQL.

### GIN indexes

`ix_<table>_custom_fields_gin` on all five tables, using **`jsonb_path_ops`**.

Chosen from the query pattern that exists, not from what JSONB can do: the list
endpoints take equality filters, which become `@>` containment in SQL, and
`jsonb_path_ops` indexes exactly that at about half the size of the default. The
key-existence operators (`?`, `?|`, `?&`) are not used anywhere in `app/`.

### capture_stage

`capture_stage` is a register COLUMN on `field_metadata`, not a field. It decides
which stage tab shows a field; the Details tab excludes every `STAGE` section.
A field with neither therefore rendered nowhere while looking correct in
Administration — which is what happened to the first two fields created through
the Round-6 UI.

Closed three ways: the value is derived from the section name on create and on a
move (`_derive_capture_stage`), the two existing NULLs were backfilled by
migration `0007`, and publish now **refuses** a pipeline field whose stage is
missing or disagrees with its section. Safe to enforce — all 133 register rows in
a numbered STAGE section already agreed, with no exceptions.

`administration`'s `STAGE DEFINITION  (configuration)` sections are untouched:
they describe stage config and are not pipeline stages, which is why the rule
matches `^STAGE [0-9]` rather than a bare prefix.

### Tests

```bash
./.venv/Scripts/python.exe test_metadata_round6.py   # 22 — the Round-6 lifecycle
./.venv/Scripts/python.exe test_custom_fields.py     # 13 — dynamic-value storage
./.venv/Scripts/python.exe test_round6_gaps.py       # 56 — the four gaps
```
