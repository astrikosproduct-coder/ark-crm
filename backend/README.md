# backend/ — placeholder

Empty on purpose.

`CLAUDE.md`'s hard rule for this project is **no backend, ever**: ARK CRM is a
browser-only clickable prototype. All data lives in `localStorage`; every `/api/...`
call is intercepted and answered by MSW from `frontend/spec/*.json`. There is no
server, no database, and nothing in this folder talks to either.

This folder exists so the monorepo *layout* is ready if that ever changes — it is
not a signal that a backend is in scope. Before writing anything here (Express,
a database client, an API route, anything that listens on a port), the "No backend"
rule in the repo-root `CLAUDE.md` has to be revisited and changed first, deliberately,
not worked around by starting here.
