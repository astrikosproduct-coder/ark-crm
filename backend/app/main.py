import os
import secrets

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .auth import require_access, require_admin
from .database import Base, engine
from .routers import (
    accounts,
    admin,
    audit_log,
    auth,
    conflicts,
    contacts,
    conversions,
    deals,
    directory,
    leads,
    metadata,
    opportunities,
    registrations,
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
#   PROTECTED   = signed in AND granted at least one role
#   ADMIN_ONLY  = signed in AND holding the ADMIN role
#
# `auth.router` is mounted with NEITHER, because it is the way in: /auth/login
# and /auth/callback must work before anyone has a session, and /auth/me must
# answer for a signed-in user who has no roles yet, or the frontend cannot tell
# them their access is pending.
PROTECTED = [Depends(require_access)]
ADMIN_ONLY = [Depends(require_admin)]

# Sign-in itself. Unauthenticated by necessity.
app.include_router(auth.router, prefix="/api")

# Mounted under /api/admin so the frontend can keep using the one axios client
# (baseURL '/api'). MSW passes /api/admin/* through untouched; every other
# /api/* path still resolves to a mock handler.
app.include_router(admin.router, prefix="/api/admin", dependencies=ADMIN_ONLY)

# The Round-6 metadata layer, at /api/admin/metadata — the field register
# itself, as data. Mounted under the existing /api/admin prefix on purpose: MSW
# already passes /api/admin/* through and Vite already proxies it, so this
# needed no new handler in src/mocks/handlers.ts and no new server.proxy entry.
#
# Mounted BEFORE the /api/admin user routes would be a problem only if a user
# could be called "metadata"; the admin router's paths are /roles and /users/*,
# so the two cannot collide.
app.include_router(metadata.router, prefix="/api/admin/metadata", dependencies=ADMIN_ONLY)

# The user directory, at /api/users. Users are a real database resource now, so
# MSW passes this path through instead of answering it from the mock store —
# every OTHER /api/* collection is still mocked. Mounted after the admin router
# so /api/admin/users can never be shadowed by /api/users/{user_id}.
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
#
# Not yet wired into the frontend — see CLAUDE.md's Round table and
# src/mocks/handlers.ts, which still answers /api/opportunities from the
# browser store. This is backend-only until the cutover.
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
#
# Not yet wired into the frontend, same as Opportunities — see CLAUDE.md's
# Round table and src/mocks/handlers.ts, which still answers /api/deals from
# the browser store. This is backend-only until the cutover.
app.include_router(deals.router, prefix="/api", dependencies=PROTECTED)

# Round 3, done out of order: deal registrations and their conflict
# adjudications. Both described by the register under module `partners`
# (sections DEAL REGISTRATION and CONFLICT ADJUDICATION), not a module of
# their own — see models.DealRegistration. Frontend already speaks these
# paths (NewRegistrationPage.tsx, ConflictPanel.tsx, ConvertToDealDialog.tsx)
# against the mock store; cut over via handlers.ts passthrough +
# vite.config.ts proxy, same as every module above.
app.include_router(registrations.router, prefix="/api", dependencies=PROTECTED)
app.include_router(conflicts.router, prefix="/api", dependencies=PROTECTED)

# Round 7's first two audit-log-shaped tables. Frontend already POSTs to both
# paths (AdvanceStageDialog.tsx/LeadAdvanceDialog.tsx/DealDetailPage.tsx to
# /transitions, LeadAdvanceDialog.tsx/opportunities/ConvertToDealDialog.tsx to
# /conversions) against the mock store — MSW's catch-all handled them until
# now. Both need their MSW handlers.ts collections removed and a
# vite.config.ts proxy entry added for the cutover to be real; see those
# files.
app.include_router(transitions.router, prefix="/api", dependencies=PROTECTED)
app.include_router(conversions.router, prefix="/api", dependencies=PROTECTED)

# The record-level CRUD trail, written from inside the five routers above —
# see app/audit.py. Not called by the frontend at all yet: there is no
# History tab reading GET /api/audit-log. Still needs a vite.config.ts proxy
# entry so /docs and any future UI can reach it; MSW never intercepted it in
# the first place since no browser-store collection named audit_log exists to
# collide with.
app.include_router(audit_log.router, prefix="/api", dependencies=PROTECTED)


@app.get("/")
def root():
    return {"message": "ARK CRM API is running"}
