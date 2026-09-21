import os
import secrets

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .auth import require_access, require_administration
from .database import Base, engine
from .routers import (
    accounts,
    admin,
    audit_log,
    auth,
    conflicts,
    contacts,
    conversions,
    dashboard,
    deals,
    feedback,
    spreadsheets,
    directory,
    leads,
    metadata,
    opportunities,
    pursuit_groups,
    registrations,
    search,
    transitions,
)

# Convenience for local start-up: creates anything missing so a fresh clone can
# run without a migration step. It is NOT how the schema evolves — Round 6
# introduced Alembic for that, and `alembic upgrade head` owns every change from
# here on. create_all only ever adds missing tables, so it is a no-op on a
# database that migrations have already brought up to date. See backend/README.md.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ARK CRM API",
    version="0.1.0",
)


# The frontend reaches this through Vite's dev proxy on /api/admin, so it is
# same-origin and CORS is not strictly needed. Kept for direct calls to :8000
# from curl, the /docs page and any future tooling.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The signed session cookie the sign-in flow writes and app/auth.py reads.
#
# SESSION_SECRET must be set and stable in any real deployment: a generated
# fallback means every restart invalidates every session, which is tolerable
# while developing and unacceptable in production, so it is loud about it.
_session_secret = os.getenv("SESSION_SECRET")
if not _session_secret:
    _session_secret = secrets.token_urlsafe(32)
    print(
        "[auth] SESSION_SECRET is not set — using a random one. "
        "Every restart will sign everybody out. Set it in backend/.env."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="ark_session",
    https_only=os.getenv("SESSION_HTTPS_ONLY", "").lower() == "true",
    same_site="lax",  # survives the redirect back from Microsoft
    max_age=60 * 60 * 12,
)


# ---------------------------------------------------------------------------
# WHERE ACCESS IS ENFORCED
# ---------------------------------------------------------------------------
# The dependency goes on the ROUTER, not on ~97 individual routes: one line per
# router cannot be forgotten when a new endpoint is added to an existing file,
# whereas a per-route decorator silently can. A route is protected because of
# where it is mounted.
#
#   PROTECTED       = signed in AND granted at least one role
#   DEVELOPER_ONLY  = signed in AND holding the DEVELOPER role — Administration,
#                     for V1 (21 Sep 2026; was ADMIN). See require_administration.
#
# `auth.router` is mounted with NEITHER, because it is the way in: /auth/login
# and /auth/callback must work before anyone has a session, and /auth/me must
# answer for a signed-in user who has no roles yet, or the frontend cannot tell
# them their access is pending.
PROTECTED = [Depends(require_access)]
DEVELOPER_ONLY = [Depends(require_administration)]

# Sign-in itself. Unauthenticated by necessity.
app.include_router(auth.router, prefix="/api")

# Administration — users, roles, the directory — at /api/admin. DEVELOPER-only
# in V1; see app/auth.py::require_administration.
app.include_router(admin.router, prefix="/api/admin", dependencies=DEVELOPER_ONLY)

# The Round-6 metadata layer, at /api/admin/metadata — the field register
# itself, as data. Under /api/admin because managing the register is
# administration, and it carries the same DEVELOPER-only gate.
#
# Mounted BEFORE the /api/admin user routes would be a problem only if a user
# could be called "metadata"; the admin router's paths are /roles and /users/*,
# so the two cannot collide.
app.include_router(metadata.router, prefix="/api/admin/metadata", dependencies=DEVELOPER_ONLY)

# The user directory, at /api/users — read by every owner lookup, so any role
# may read it. Mounted after the admin router so /api/admin/users can never be
# shadowed by /api/users/{user_id}.
app.include_router(directory.router, prefix="/api", dependencies=PROTECTED)

# Accounts, at /api/accounts — the second real database-backed module. Both
# End Clients and Partners are rows in this one table; Partners is a filtered
# view over it, not a collection of its own.
app.include_router(accounts.router, prefix="/api", dependencies=PROTECTED)

# Contacts, at /api/contacts — the external people at those accounts. Round 1's
# final table. contacts.account is a real FK to accounts.account_id.
app.include_router(contacts.router, prefix="/api", dependencies=PROTECTED)

# Leads, at /api/leads — Round 2's table. Every lookup here is a real FK into
# accounts, users, contacts or leads itself; the columns that will eventually
# point at Round 3-5 tables (deal registrations, deals, products, POCs, gates)
# stay plain id columns until those tables exist.
app.include_router(leads.router, prefix="/api", dependencies=PROTECTED)

# Opportunities, at /api/opportunities — Round 3's table. parent_lead is a
# real FK into leads.lead_id; the Leads table may still be empty, which the
# constraint does not require — it only rejects a parent_lead value that
# names a Lead which doesn't exist. bid_record, primary_quote and
# commercial_gate stay plain id columns, same reasoning as Leads' own
# poc_record/ctb_gate, until bids/quotes/gates exist as tables.
app.include_router(opportunities.router, prefix="/api", dependencies=PROTECTED)

# Deals, at /api/deals — Round 4/5's table. parent_lead and parent_opportunity
# are real FKs into leads.lead_id and opportunities.opportunity_id
# respectively (a Deal carries at most one, depending which conversion path
# created it — see models.Deal); delivery_pm/end_client/customer_partner_si
# are real FKs into users/accounts. deal_bid_commitments and
# deal_expansion_use_cases are real child tables — see models.Deal's
# docstring for why the register's flat guarantee_—_* fields are the former's
# row shape rather than scalars on Deal itself, confirmed against
# spec/extensions.json and src/lib/spec/childSpec.ts's isChildColumnOnly()
# before this table was written, not assumed.
app.include_router(deals.router, prefix="/api", dependencies=PROTECTED)

# Round 3, done out of order: deal registrations and their conflict
# adjudications. Both described by the register under module `partners`
# (sections DEAL REGISTRATION and CONFLICT ADJUDICATION), not a module of
# their own — see models.DealRegistration.
app.include_router(registrations.router, prefix="/api", dependencies=PROTECTED)
app.include_router(conflicts.router, prefix="/api", dependencies=PROTECTED)

# Pursuit Groups, at /api/pursuit-groups — one project at one End Client pursued
# through more than one partner, of which only the primary counts toward
# pipeline (Playbook §7.2). PROTECTED, not admin-only, by decision on 13 Sep
# 2026: the workflow is settled first, and becomes Admin-only when role-based
# permissions are built. See app/pursuits.py.
app.include_router(pursuit_groups.router, prefix="/api", dependencies=PROTECTED)

# Stage transitions and conversions — the record of every stage move, skip,
# reversal and conversion, with its reason.
app.include_router(transitions.router, prefix="/api", dependencies=PROTECTED)
app.include_router(conversions.router, prefix="/api", dependencies=PROTECTED)

# The record-level CRUD trail, written from inside the five routers above —
# see app/audit.py. Read by each record's History tab.
app.include_router(audit_log.router, prefix="/api", dependencies=PROTECTED)

# The management dashboard, at /api/dashboard — read-only aggregates over the
# live pipeline, computed with app/revenue.py's rule so its totals reconcile
# with the boards. PROTECTED like every data router: anyone with a role sees it
# until role-based permissions are built. Needs the handlers.ts passthrough and
# the vite.config.ts proxy entry, both.
app.include_router(dashboard.router, prefix="/api", dependencies=PROTECTED)

# Global search, at /api/search — the header box, across every live module in
# one request. PROTECTED like the modules it reads, and exactly as readable as
# they are; when profiles arrive it needs a per-module filter of its own. Needs
# the handlers.ts passthrough and the vite.config.ts proxy entry, both.
app.include_router(search.router, prefix="/api", dependencies=PROTECTED)

# User feedback, at /api/feedback (UX roadmap item 2, 17 Sep 2026). PROTECTED so
# anyone with a role can send it; reading and triage are DEVELOPER-only, checked
# per route by require_developer because they share this router with the POST.
# Needs the handlers.ts passthrough and the vite.config.ts proxy entry, both.
app.include_router(feedback.router, prefix="/api", dependencies=PROTECTED)

# Excel / CSV import and export, at /api/spreadsheets/{module} (UX roadmap item
# 4, 17 Sep 2026). Every imported row goes through the module's own create
# route; see app/spreadsheets/importer.py. Needs the handlers.ts passthrough and
# the vite.config.ts proxy entry, both.
app.include_router(spreadsheets.router, prefix="/api", dependencies=PROTECTED)


@app.get("/")
def root():
    return {"message": "ARK CRM API is running"}
