# frontend/player/

## Purpose
The Player React app (Vite + TypeScript + Tailwind), packaged as its own npm project. It is the
mobile client students use to join and answer; see `src/CLAUDE.md` for how the app works.

## Contents
- `src/` — all application code; see `src/CLAUDE.md`.
- `index.html` — Vite entry page (title "Buzzer"), loads `/src/main.tsx`. The viewport meta disables
  pinch-zoom (`maximum-scale=1.0, user-scalable=no`).
  Before any script loads, a small inline script sets `<html data-theme>` and `color-scheme`
  from `localStorage['buzzer-theme']` (else the OS preference) so there is no flash of the wrong
  theme; `<meta name="theme-color" content="">` starts empty and `initTheme()` fills it. (T9)
- `package.json` — scripts `dev` (Vite on :5174), `build` (`tsc -b && vite build`), `preview`.
  Same dependencies as the host minus `qrcode.react`: react 18, react-router-dom 6,
  socket.io-client 4, lucide-react, clsx + tailwind-merge. Script `test` (`vitest run`); dev
  dependencies include vitest and jsdom (only `src/lib/theme.test.ts` uses a DOM; the rest run
  in node).
- `vite.config.ts` — `base` is `/player/` for production builds and `/` in dev; the dev server
  proxies `/api` and `/socket.io` (with WebSocket upgrade) to `http://localhost:8000`.
- `tsconfig.json` / `tsconfig.node.json` / `tailwind.config.ts` / `postcss.config.js` — identical
  to the host's (strict TypeScript with unused-variable errors; Tailwind scans `index.html` +
  `src/`, adds the theme colours from `src/theme/colors.js` and sets
  `future.hoverOnlyWhenSupported`).
- `dist/` — build output (git-ignored), bind-mounted into the nginx container.

## How it fits in
Run it with `npm run dev:player` (or `npm run dev` for all three) from the repo root. In dev the
browser talks to Vite on :5174, which proxies API and socket traffic to the Dockerised backend.
For :8080, `npm run build` writes `dist/`, which docker-compose mounts at
`/usr/share/nginx/html/player`; nginx serves it under `/player/` with an SPA fallback to
`/player/index.html`, and `http://localhost:8080/` redirects to `/player/`.

## Gotchas
- **The theme script in `index.html` must match `src/theme/theme.ts`** (same storage key, only
  `light` / `dark` count). It writes no colour values: a hex there fails the raw-colour test.
- **The host's QR code only works against :8080.** It links to `<host origin>/player/join?code=…`.
  In dev that origin is the host's Vite server, and even on :5174 the dev build has no `/player/`
  prefix, so the link falls through to `/join` and the room code is lost.
- **Testing on a real phone:** `localhost` on the phone is the phone. Use the laptop's LAN IP, and
  note that Vite only listens on localhost unless started with `--host`.
- **`dist/` is a snapshot.** :8080 shows the last build; rerun `npm run build`. An empty `dist/`
  makes nginx return 403.
- **Stale compiled configs:** `tsc -b` emits git-ignored `vite.config.js` / `tailwind.config.js`
  (+ `.d.ts`) next to the `.ts` files, and Vite and Tailwind load the `.js` first. Edits to the
  `.ts` configs don't apply until the next build regenerates them.
- CI (`frontend-typecheck` in `.gitlab-ci.yml`) runs `npx tsc --noEmit` here; there is no linter
  or formatter. `npm test` runs vitest (the number parser, display helpers and `theme.ts`, in
  `src/lib/`); CI does not run it yet.
- Disabling pinch-zoom in `index.html` is an accessibility trade-off; change it deliberately.
- Shares nothing with `frontend/host` or `frontend/admin`: separate `node_modules`, configs, and
  copies of `lib/` and `components/ui/`.
