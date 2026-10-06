# frontend/host/src/lib/

## Purpose
Shared helpers for the host app: the REST client, the Tailwind class-merging helper, and the
pure logic behind the T7 question types (numeric_estimate bars and the plot_point plane).

## Contents
- `api.ts` — `api.get/post/put/patch/delete` over `fetch`, prefixed with `/api`, plus
  `postForm(path, FormData)` / `putForm` (multipart upload or replace; the browser sets the boundary) and
  `download(path)` (authenticated GET saved as a file, name from `Content-Disposition`). Attaches
  `Authorization: Bearer <localStorage.token>` when present and returns `{}` for empty bodies
  (204). Errors throw `Error(text)` where `text` is, in order: `body.message`, `body.detail` if a
  string, the joined `msg` fields of a 422 `detail` array, else `HTTP <status>`.
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`, used by every `components/ui` primitive.
- `numericEstimate.ts` — (T7) numeric_estimate band bars and target text for the results screens.
- `plotGeometry.ts` — (T7 plot_point) pure plane geometry (grid size, grid ↔ graph ↔ pixel,
  snapping, cell distance, line and polynomial clipping, `formatCoord`). **Byte-identical to the
  player's copy**; `tests/unit/test_plot_geometry_copies.py` fails if they drift. Imports nothing;
  its tests live in the player app (the host has no test runner).
- `plotPalette.ts` — every canvas colour (plane, answer dots, target star, band squares) in one
  place; T9 switches these to theme tokens.
- `plotDraw.ts` — paints the plane (background image, grid, axes, tick labels, overlays). The
  host's own copy of the player's drawing code, with a `scale` that enlarges text for the
  projector.
- `plotPoint.ts` — `plotConfigOf`, `plotRevealOf` and `targetText` ("(3, −2)", snapped so float
  noise never shows).
- `promptMarkup.ts` — parses a question prompt for display: the four tags the backend keeps
  (`<b>`, `<i>`, `<u>`, `<br>`) become nodes and the entities it stores (`&lt;`, `&amp;`, …) are
  decoded; anything else stays plain text. **Byte-identical to the player's copy**
  (`tests/unit/test_prompt_markup_copies.py`); tests in `promptMarkup.test.ts`. Imports nothing.
- `images.ts` — (T8) `imageUrl(id, version?)` → `/api/images/{id}` (`?v=<sha256>` in the editor,
  so a replaced image is not served from the 60 s browser cache). Question `config` may carry
  `image_id` and `option_image_ids` (parallel to `options`); see `types/game.ts` `QuestionConfig`.

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
- `download` reads the whole file into memory before saving. It adds the link to the document
  and revokes the object URL a second after `click()`; Firefox needs both.
- No 401 handling or token refresh. An expired token surfaces as a page-level error message;
  `App.tsx`'s `RequireAuth` only checks that a token *exists*.
- The token lives in `localStorage['token']`, shared with the Socket.io auth callback. Logout
  (in `HomePage`) just deletes it.
- `LoginPage`'s OAuth temp-token exchange uses raw `fetch` (it needs a different bearer token), not `api`.
- The player and admin apps have their own copies of this folder; they are not shared.
