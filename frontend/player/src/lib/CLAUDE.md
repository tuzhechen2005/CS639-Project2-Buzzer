# frontend/player/src/lib/

## Purpose
Small shared helpers for the player app: the REST client, the Tailwind class helper, a
client-side JWT expiry check, and the pure logic behind the T7 question types (number parsing,
numeric_estimate text, and the plot_point plane).

## Contents
- `api.ts` — `api.get/post` over `fetch`, prefixed with `/api`. Attaches
  `Authorization: Bearer <localStorage.token>` when present, sends JSON, returns `{}` for empty
  bodies. Errors throw `Error(text)` where `text` is, in order: `body.message`, `body.detail` if
  a string, the joined `msg` fields of a 422 `detail` array, else `HTTP <status>` — so guest-join
  and login failures show the backend's reason.
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`, plus `isTokenExpired(token)`: decodes the JWT
  payload (no signature check) and returns true if it is missing, malformed, or past `exp`.
- `parseNumber.ts` / `numericEstimate.ts` — (T7) what a player types into a number, and the
  numeric_estimate result text. Tested by `*.test.ts` (vitest, `npm test`).
- `plotGeometry.ts` — (T7 plot_point) pure plane geometry: grid size, grid ↔ graph ↔ pixel (y
  flipped), snapping (midway rounds up), cell distance, line and polynomial clipping,
  `roundToStep` / `formatCoord` (typographic minus). **Byte-identical to the host's copy**;
  `tests/unit/test_plot_geometry_copies.py` fails if they drift. Imports nothing.
- `plotPalette.ts` — every canvas colour in one place. `plotPalette()` builds them from the
  theme tokens on every call (`tokenColor` from `../theme/theme`), so callers must call it at
  draw time, not cache it.
- `theme.test.ts` — (T9) vitest (jsdom) for `src/theme/theme.ts`: stored choice vs OS, invalid
  or blocked storage, `applyTheme` (attribute, `color-scheme`, meta tag, `themechange`), OS
  changes only while nothing is stored. It lives here, not in `src/theme/`, because that folder
  must stay byte-identical across the three apps.
- `plotDraw.ts` — paints the plane on a canvas: background image, grid, axes, tick labels,
  overlays, the player's point; `planeDescription` for the `aria-label`.
- `plotPoint.ts` — the plot_point rules that are not drawing: the "Type coordinates" commit
  rules (`commitAxis`, `commitForSubmit`, `canSubmitTyped`, `flipSign`) and the result text
  (`plotResultLine`, `plotVerdict`). Tested by `plotPoint.test.ts`; `plotGeometry.test.ts` tests
  the geometry.
- `promptMarkup.ts` — parses a question prompt for display: the four tags the backend keeps
  (`<b>`, `<i>`, `<u>`, `<br>`) become nodes and the entities it stores (`&lt;`, `&amp;`, …) are
  decoded; anything else stays plain text. **Byte-identical to the host's copy**
  (`tests/unit/test_prompt_markup_copies.py`); tests in `promptMarkup.test.ts`. Imports nothing.
- `images.ts` — (T8) `imageUrl(id)` → `/api/images/{id}`. Question `config` may carry
  `image_id` and `option_image_ids` (parallel to `options`); see `types/game.ts` `QuestionConfig`.

## How it fits in
Pages use `api` for the pre-game REST calls only: room ping (`/game/rooms/:code/ping`), guest
join (`/auth/guest`), and local login (`/auth/login`). `isTokenExpired` decides whether
`NamePage` offers sign-in options and whether `GameLayout` will connect at all. Live game traffic
goes over Socket.io in `pages/game/GameLayout.tsx`, not through here.

## Gotchas
- The error-text order matches the backend's two error shapes (see
  `backend/app/common/CLAUDE.md`) and the host and admin copies; keep them in step. Roster
  rejection on join is not a REST error — it arrives as a socket `error` event in `GameLayout`.
- Not the same as the host's `lib/`: no `delete` helper, and `isTokenExpired` exists only here.
  Fixes made in one app's copy don't reach the other.
- `isTokenExpired` only reads the `exp` claim; a token the server would reject for other reasons
  (bad signature, rotated keys after a backend restart without fixed JWT keys) still looks valid.
- There is no refresh flow; an expired token sends the player back to `NamePage`.
- `LoginPage`'s OAuth temp-token exchange uses raw `fetch`, not `api` (different bearer token).
