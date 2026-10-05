# frontend/admin/src/lib/

## Purpose
Shared helpers for the admin app: the REST client (the fullest of the three apps' copies) and the
Tailwind class helper.

## Contents
- `api.ts` — `api.get/post/put/patch/delete` over `fetch`, prefixed with `/api`, bearer token from
  `localStorage['token']`, JSON bodies; throws `Error(body.detail)`, falling back to
  `Error("HTTP <status>")`, and returns `{}` for empty (204) bodies. Two extras:
  - `postForm(path, FormData)` — multipart upload with no `Content-Type` header, so the browser
    sets the boundary. Used for game JSON import.
  - `download(path)` — authenticated GET that saves the response as a file, using the filename
    from `Content-Disposition` (falls back to `download`). Used for game export, session
    CSV/Canvas export and the HTML report.
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`. Identical to the host's.

## How it fits in
Every admin page talks to the backend only through `api`; almost all paths are under
`/admin/*` (guarded by `require_admin` on the backend). There is no Socket.io in the admin app.

## Gotchas
- **Backend error messages are lost.** `apiFetch` reads `body.detail`, but most backend errors
  (`BuzzerError`: 401/403/404/409) send `{error, message}`, so the user sees a bare
  `HTTP 401` / `HTTP 403` instead of e.g. "Invalid credentials". Validation errors (422) put an
  *array* in `detail`, which shows as `[object Object]`. Only plain `HTTPException`s (e.g. game
  import) come through readably. See `backend/app/common/CLAUDE.md`.
- `postForm` and `download` duplicate the error handling of `apiFetch` rather than sharing it;
  change all three together.
- No 401 handling or refresh: an expired or non-admin token shows up as a per-page
  `HTTP 401` / `HTTP 403` error (not the backend's "Admin access required" text), not a redirect to login. `App.tsx`'s `RequireAdmin` only checks
  that *a* token exists, so a host's login gets into the dashboard and then fails on every page.
- `download` reads the whole file into memory as a blob before saving, and revokes the object URL
  immediately after `click()`.
- The host and player apps have their own, smaller copies of this folder.
