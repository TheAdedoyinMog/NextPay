# 0012. Mobile app foundation

- Status: Accepted
- Date: 2026-11-04

## Context
Phase 3 builds the MVP app on the API from Phase 2. It is developed on Windows with no Mac,
so there is no iOS Simulator and no local iOS build; testing happens on a physical iPhone.
The app handles financial data but must never become a second place where money is
calculated (ADR 0001, ground rule 1).

## Decision

### Platform
- **Expo (latest stable SDK), React Native, TypeScript in strict mode**, in `mobile/`, with
  Expo Router for navigation.
- **An EAS development build is the main dev target, not Expo Go.** Expo Go only runs the
  native modules it ships with and cannot carry our own config. A development build is our
  own app with a dev menu, built in Expo's cloud, which is the only way to get an iOS build
  from Windows. JavaScript changes still load instantly from Metro; a new build is only
  needed when native code or native config changes.

### API contract
- **Types are generated, never written by hand.** `backend/scripts/export_openapi.py`
  imports the FastAPI app and writes `openapi.json` with no server or database running;
  `openapi-typescript` turns it into `mobile/src/api/schema.d.ts`.
- **`schema.d.ts` is committed; `openapi.json` is not.** The generated types are what the
  app compiles against, and their diff shows a reviewer what changed in the contract. The
  JSON is only a step on the way. CI regenerates the file and fails if it differs.
- **All HTTP goes through one module, `src/api/client.ts`**, using `openapi-fetch`. It owns
  the base URL, the auth header hook, and error mapping: every failure becomes an
  `ApiError` with the backend's `code` and `message`, or `network_error` when no response
  arrived. A validation `message` already names the bad fields, so it reaches the user
  intact. That is how a missing nullable field on `PUT` stays obvious (ADR 0010): the types
  demand `T | null`, and a 422 says which field.

### Client state
- **TanStack Query holds server state.** Query hooks are written by hand per feature in
  `features/<name>/api.ts`, with explicit query keys and invalidation. Generated hooks would
  hide the invalidation rules, which are the part worth reading.
- **Session tokens live in `expo-secure-store`, and there is no Redux or other global
  store.** With server state in the query cache, what remains is small enough for React
  state and context. Secure storage itself arrives with sign-in; this milestone adds only
  the hook that supplies a token to the client.
- **Mutations are not retried.** POST is not idempotent until idempotency keys exist
  (ADR 0010), so an automatic retry could create a duplicate.

### Structure and money
- **Feature folders** (`features/bills`, `features/goals`, ...). Routes in `src/app/` only
  display data and hand user actions to hooks.
- **The app never does financial math.** Money arrives as integer cents. `formatCents` is
  the only money code in the app, and it works on the digits rather than dividing, so no
  float is ever involved. It throws on a non-integer, because that means a bug upstream.

### Reaching a local backend from the phone
**Same Wi-Fi, using the PC's LAN address, with a Windows Firewall rule limited to private
networks.** Metro has to be reachable from the phone over the LAN in any case, so a tunnel
for the API alone would add a dependency without removing the firewall step. In development
the client takes the host from Metro's address and adds port 8000, so nothing needs editing
when the PC's IP changes. `EXPO_PUBLIC_API_URL` overrides this, for a tunnel on networks
that block device-to-device traffic, and later for real environments.

## Consequences
- A backend contract change shows up as a compile error in the app, or as a CI failure if
  the types were not regenerated. The mobile CI job therefore needs Python as well as Node.
- Physical-device iOS builds need a paid Apple Developer Program membership, because EAS
  signs them with an ad hoc provisioning profile. This is a cost we accept for having no Mac.
- Free-plan EAS builds are queued and limited per month, so native changes should be batched.
- Testing on a phone requires the backend to listen on all interfaces (`--host 0.0.0.0`) on
  a trusted network. That is a development-only command; the firewall rule keeps it off
  public networks.
- Plain HTTP to a LAN address is acceptable only for development. Hosting (ADR 0007) must
  provide HTTPS before any non-development build ships.
