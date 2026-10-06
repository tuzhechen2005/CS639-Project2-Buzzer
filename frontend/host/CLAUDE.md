# frontend/host/

## Purpose
The Host React app (Vite + TypeScript + Tailwind), packaged as its own npm project. It is the
instructor's app: course management (games, questions, roster, past sessions) and the big-screen
game display; see `src/CLAUDE.md` for how the app itself works.

## Contents
- `src/` — all application code; see `src/CLAUDE.md`.
- `index.html` — Vite entry page (title "Buzzer — Host"), loads `/src/main.tsx`.
- `package.json` — scripts `dev` (Vite on :5173), `build` (`tsc -b && vite build`), `preview`.
  Runtime deps: react 18, react-router-dom 6, socket.io-client 4, qrcode.react, lucide-react,
  clsx + tailwind-merge.
- `vite.config.ts` — `base` is `/host/` for production builds and `/` in dev; the dev server
  proxies `/api` and `/socket.io` (with WebSocket upgrade) to `http://localhost:8000`.
- `tsconfig.json` — strict mode, `noUnusedLocals` / `noUnusedParameters`, `noEmit`; covers `src/`.
  `tsconfig.node.json` covers the two config files.
- `tailwind.config.ts` / `postcss.config.js` — Tailwind scans `index.html` and `src/**/*.{ts,tsx}`;
  only customisation is the system font stack.
- `dist/` — build output (git-ignored), bind-mounted into the nginx container.

## How it fits in
Run it with `npm run dev:host` (or `npm run dev` for all three apps) from the repo root, which
wraps this package's scripts. In dev, the browser talks to Vite on :5173 and Vite proxies API and
socket traffic to the Dockerised backend. For :8080, `npm run build` writes `dist/`, which
docker-compose mounts at `/usr/share/nginx/html/host`; nginx serves it under `/host/` with an
SPA fallback to `/host/index.html` and proxies `/api` and `/socket.io` to the backend.

## Gotchas
- **`dist/` is a snapshot.** :8080 shows whatever was last built; rerun `npm run build` to update it.
  If `dist/` is empty, nginx returns 403 for `/host/`. If Docker created `dist/` as root, the build
  fails with `EACCES` (fix in the root README).
- **Stale compiled configs:** `tsc -b` emits `vite.config.js` / `.d.ts` and `tailwind.config.js` /
  `.d.ts` next to the `.ts` sources (they're git-ignored). Vite and Tailwind load the `.js` file
  *before* the `.ts` one, so an edit to `vite.config.ts` or `tailwind.config.ts` is ignored until
  the next `npm run build` regenerates them (or you delete the `.js` copies).
- `npm run build` type-checks with strict unused-variable rules, so code that runs fine in
  `npm run dev` can still fail the build. CI (`frontend-typecheck` in `.gitlab-ci.yml`) runs
  `npx tsc --noEmit` here on every MR; run it locally before pushing.
- If :5173 is taken, Vite silently picks the next port; check the terminal output.
- There is no linter, formatter or test runner for this package; type-checking is the only gate.
- This package shares nothing with `frontend/player` or `frontend/admin`; each has its own
  `node_modules`, configs and copies of `lib/` and `components/ui/`.
