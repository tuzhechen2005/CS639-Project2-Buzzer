# frontend/admin/src/lib/

## Purpose
Shared helpers for the admin app: the REST client and the Tailwind class helper.

## Contents
- `api.ts` — `api.get/post/put/patch/delete` over `fetch`, prefixed with `/api`, bearer token from
  `localStorage['token']`, JSON bodies; returns `{}` for empty (204) bodies. Errors throw
  `Error(text)` where `text` is, in order: `body.message`, `body.detail` if a string, the joined
  `msg` fields of a 422 `detail` array, else `HTTP <status>`. Two extras:
  - `postForm(path, FormData)` — multipart upload with no `Content-Type` header, so the browser
    sets the boundary. (No admin page uploads since T4; kept for parity with the host copy.)
  - `download(path)` — authenticated GET that saves the response as a file, using the filename
    from `Content-Disposition` (falls back to `download`). Used for session CSV/Canvas export and
    the HTML report.
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`. Identical to the host's.

## How it fits in
Every admin page talks to the backend only through `api`; almost all paths are under
`/admin/*` (guarded by `require_admin` on the backend). There is no Socket.io in the admin app.

## Gotchas
- The error-text order matches the backend's two error shapes (`{error, message}` and
  `{error, detail: [...]}`; see `backend/app/common/CLAUDE.md`). All three request paths share
  one `throwForStatus`; keep the host and player copies in step.
- No 401 handling or refresh: an expired or non-admin token shows up as a per-page error (e.g.
  "Admin access required"), not a redirect to login. `App.tsx`'s `RequireAdmin` only checks that
  *a* token exists, so a host's login gets into the dashboard and then fails on every page.
- `download` reads the whole file into memory as a blob before saving, and revokes the object URL
  immediately after `click()`.
- The host app has an equivalent copy (same methods); the player's is smaller. They are copies,
  not shared code.
