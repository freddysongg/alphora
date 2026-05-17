# Alphora

Research desk for US equities.

## Monorepo layout

- `apps/web` — Next.js 16 frontend (App Router, React Server Components, TypeScript, Tailwind v4)
- `services/api` — FastAPI backend (scaffold pending)
- `.context` — working documents, plans, references, and design assets
- `docs` — published documentation
- `tests` — cross-package integration tests

## Scripts

Run from repo root:

- `npm run dev` — start the web app in development mode
- `npm run build` — production build of the web app
- `npm run lint` — lint the web app
- `npm run typecheck` — typecheck the web app
