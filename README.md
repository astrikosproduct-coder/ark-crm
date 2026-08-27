# ARK CRM

A clickable prototype of ARK CRM for Astrikos. See [`CLAUDE.md`](./CLAUDE.md) for the
full brief — what this is, the hard rules (**no backend, ever** — this is a
browser-only prototype), the domain model and the pipeline it walks through.

## Layout

```
.
├── frontend/   React + TypeScript + Vite app — the entire prototype today.
│               Data is mocked by MSW from spec/*.json; see frontend/README.md.
├── backend/    Placeholder only. Empty on purpose — CLAUDE.md's hard rule is
│               "no backend, ever." Do not add a server here without first
│               updating that rule; see backend/README.md.
├── docs/       Reference screenshots and other non-code project artifacts.
├── CLAUDE.md   Governs this repo. Read it before changing anything.
└── README.md   This file.
```

## Getting started

```bash
cd frontend
npm install
npm run dev
```

That's the whole setup — there is nothing to run outside `frontend/`.

## Scripts

From the repo root:

| Command | What it does |
|---|---|
| `npm run dev` | Starts the frontend dev server (proxies into `frontend/`) |
| `npm run build` | Type-checks and builds the frontend (proxies into `frontend/`) |
| `npm run lint` | Lints the frontend (proxies into `frontend/`) |

Each just `cd`s into `frontend/` and runs the matching script there. There is
no npm workspace set up — `frontend/node_modules` is exactly what `npm install`
inside `frontend/` produced, untouched by anything at the root.
