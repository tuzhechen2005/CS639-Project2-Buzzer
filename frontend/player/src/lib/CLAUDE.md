# frontend/player/src/lib/

## Purpose
Small shared helpers for the player app: the REST client, the Tailwind class helper, and a
client-side JWT expiry check.

## Contents
- `api.ts` — `api.get/post` over `fetch`, prefixed with `/api`. Attaches
  `Authorization: Bearer <localStorage.token>` when present, sends JSON, throws `Error(detail)`
  from FastAPI's error body (or `HTTP <status>`), returns `{}` for empty bodies.
- `utils.ts` — `cn(...)` = `twMerge(clsx(...))`, plus `isTokenExpired(token)`: decodes the JWT
  payload (no signature check) and returns true if it is missing, malformed, or past `exp`.

## How it fits in
Pages use `api` for the pre-game REST calls only: room ping (`/game/rooms/:code/ping`), guest
join (`/auth/guest`), and local login (`/auth/login`). `isTokenExpired` decides whether
`NamePage` offers sign-in options and whether `GameLayout` will connect at all. Live game traffic
goes over Socket.io in `pages/game/GameLayout.tsx`, not through here.

## Gotchas
- Not the same as the host's `lib/`: no `delete` helper, and `isTokenExpired` exists only here.
  Fixes made in one app's copy don't reach the other.
- `isTokenExpired` only reads the `exp` claim; a token the server would reject for other reasons
  (bad signature, rotated keys after a backend restart without fixed JWT keys) still looks valid.
- There is no refresh flow; an expired token sends the player back to `NamePage`.
- `LoginPage`'s OAuth temp-token exchange uses raw `fetch`, not `api` (different bearer token).
