# frontend/host/src/lib/

## Purpose
Tiny shared helpers for the host app: the REST client and the Tailwind class-merging helper.

## Contents
- `api.ts` — `api.get/post/delete` over `fetch`, prefixed with `/api`. Attaches
  `Authorization: Bearer <localStorage.token>` when present, always sends JSON, throws
  `Error(body.detail)`, falling back to `Error("HTTP <status>")`, and returns `{}` for empty bodies (204).
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`, used by every `components/ui` primitive.

## How it fits in
Pages call `api` for REST only (login, `/game/my-courses`, `/game/my-games`, `/game/my-active-sessions`,
`/game/rooms`, session delete). Live game traffic does not go through here; it uses the Socket.io
client created in `pages/game/GameLayout.tsx`. `/api` is relative, so it works both behind nginx
(:8080) and through the Vite dev proxy.

## Gotchas
- **Backend error messages are lost.** `apiFetch` reads `body.detail`, but most backend errors
  (`BuzzerError`: 401/403/404/409) send `{error, message}`, so the user sees a bare
  `HTTP 401` / `HTTP 403` instead of e.g. "Invalid credentials". Validation errors (422) put an
  *array* in `detail`, which shows as `[object Object]`. Only plain `HTTPException`s (e.g. game
  import) come through readably. See `backend/app/common/CLAUDE.md`.
- No `put`/`patch` helper; add one here rather than calling `fetch` directly.
- No 401 handling or token refresh. An expired token surfaces as a page-level `HTTP 401` error;
  `App.tsx`'s `RequireAuth` only checks that a token *exists*.
- The token lives in `localStorage['token']`, shared with the Socket.io auth callback. Logout
  (in `HomePage`) just deletes it.
- `LoginPage`'s OAuth temp-token exchange uses raw `fetch` (it needs a different bearer token), not `api`.
- The player and admin apps have their own copies of this folder; they are not shared.
