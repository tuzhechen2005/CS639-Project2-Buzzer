# frontend/host/src/lib/

## Purpose
Tiny shared helpers for the host app: the REST client and the Tailwind class-merging helper.

## Contents
- `api.ts` — `api.get/post/put/patch/delete` over `fetch`, prefixed with `/api`, plus
  `postForm(path, FormData)` (multipart upload; the browser sets the boundary) and
  `download(path)` (authenticated GET saved as a file, name from `Content-Disposition`). Attaches
  `Authorization: Bearer <localStorage.token>` when present and returns `{}` for empty bodies
  (204). Errors throw `Error(text)` where `text` is, in order: `body.message`, `body.detail` if a
  string, the joined `msg` fields of a 422 `detail` array, else `HTTP <status>`.
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`, used by every `components/ui` primitive.

## How it fits in
Pages call `api` for REST only: login, `/game/my-courses`, `/game/my-active-sessions`,
`/game/rooms`, session delete, and the course pages' `/courses/…`, `/games/…`, `/sessions/…`
endpoints (`postForm` for game import, `download` for exports and reports). Live game traffic does not go through here; it uses the Socket.io
client created in `pages/game/GameLayout.tsx`. `/api` is relative, so it works both behind nginx
(:8080) and through the Vite dev proxy.

## Gotchas
- The error-text order above matches the backend's two error shapes (`{error, message}` from
  `BuzzerError`, `{error, detail: [...]}` from validation; see `backend/app/common/CLAUDE.md`).
  Keep it in sync with the admin and player copies.
- `download` reads the whole file into memory before saving and revokes the object URL right
  after `click()`.
- No 401 handling or token refresh. An expired token surfaces as a page-level error message;
  `App.tsx`'s `RequireAuth` only checks that a token *exists*.
- The token lives in `localStorage['token']`, shared with the Socket.io auth callback. Logout
  (in `HomePage`) just deletes it.
- `LoginPage`'s OAuth temp-token exchange uses raw `fetch` (it needs a different bearer token), not `api`.
- The player and admin apps have their own copies of this folder; they are not shared.
