# frontend/host/src/lib/

## Purpose
Tiny shared helpers for the host app: the REST client and the Tailwind class-merging helper.

## Contents
- `api.ts` — `api.get/post/delete` over `fetch`, prefixed with `/api`. Attaches
  `Authorization: Bearer <localStorage.token>` when present, always sends JSON, throws
  `Error(detail)` from FastAPI's error body (or `HTTP <status>`), and returns `{}` for empty bodies (204).
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`, used by every `components/ui` primitive.

## How it fits in
Pages call `api` for REST only (login, `/game/my-courses`, `/game/my-games`, `/game/my-active-sessions`,
`/game/rooms`, session delete). Live game traffic does not go through here; it uses the Socket.io
client created in `pages/game/GameLayout.tsx`. `/api` is relative, so it works both behind nginx
(:8080) and through the Vite dev proxy.

## Gotchas
- No `put`/`patch` helper; add one here rather than calling `fetch` directly.
- No 401 handling or token refresh. An expired token surfaces as a page-level error string;
  `App.tsx`'s `RequireAuth` only checks that a token *exists*.
- The token lives in `localStorage['token']`, shared with the Socket.io auth callback. Logout
  (in `HomePage`) just deletes it.
- `LoginPage`'s OAuth temp-token exchange uses raw `fetch` (it needs a different bearer token), not `api`.
- The player and admin apps have their own copies of this folder; they are not shared.
