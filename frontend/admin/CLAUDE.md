# frontend/admin/

## Purpose
The Admin React app (Vite + TypeScript + Tailwind), packaged as its own npm project. It is the
desktop dashboard for setting up courses, users, games and questions and for exporting results;
see `src/CLAUDE.md` for how the app works.

## Contents
- `src/` — all application code; see `src/CLAUDE.md`.
- `index.html` — Vite entry page (title "Buzzer Admin"), loads `/src/main.tsx`.
- `package.json` — scripts `dev` (Vite on :5175), `build` (`tsc -b && vite build`), `preview`.
  Dependencies are the host's minus `qrcode.react` and `socket.io-client`: react 18,
  react-router-dom 6, lucide-react, clsx + tailwind-merge.
- `vite.config.ts` — `base` is `/admin/` for production builds and `/` in dev; the dev server
  proxies only `/api` to `http://localhost:8000` (no `/socket.io`, since the admin app is REST-only).
- `tsconfig.json` / `tsconfig.node.json` / `tailwind.config.ts` / `postcss.config.js` — identical
  to the host's (strict TypeScript with unused-variable errors; Tailwind scans `index.html` + `src/`).
- `dist/` — build output (git-ignored), bind-mounted into the nginx container.

## How it fits in
Run it with `npm run dev:admin` (or `npm run dev` for all three) from the repo root. In dev the
browser talks to Vite on :5175, which proxies API calls to the Dockerised backend. For :8080,
`npm run build` writes `dist/`, which docker-compose mounts at `/usr/share/nginx/html/admin`;
nginx serves it under `/admin/` with an SPA fallback to `/admin/index.html`. Log in with the
`ADMIN_USERNAME` / `ADMIN_PASSWORD` the backend bootstraps from `.env`.

## Gotchas
- **No socket support by design.** If a future admin feature needs live updates, it must add
  `socket.io-client` and a `/socket.io` proxy entry in `vite.config.ts`; neither exists today.
- **`dist/` is a snapshot.** :8080 shows the last build; rerun `npm run build`. An empty `dist/`
  makes nginx return 403.
- **Stale compiled configs:** `tsc -b` emits git-ignored `vite.config.js` / `tailwind.config.js`
  (+ `.d.ts`) next to the `.ts` files, and Vite and Tailwind load the `.js` first. Edits to the
  `.ts` configs don't apply until the next build regenerates them.
- CI (`frontend-typecheck` in `.gitlab-ci.yml`) runs `npx tsc --noEmit` here; there is no linter,
  formatter or test runner.
- The layout is desktop-only (fixed-width sidebar); it isn't designed for phones.
- Shares nothing with `frontend/host` or `frontend/player`: separate `node_modules`, configs, and
  copies of `lib/` and `components/ui/`.
