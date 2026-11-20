# NextPay mobile

The Expo + React Native + TypeScript app. Decisions are in
[ADR 0012](../docs/adr/0012-mobile-app-foundation.md) (foundation),
[ADR 0013](../docs/adr/0013-mobile-sessions.md) (sign-in and sessions) and
[ADR 0014](../docs/adr/0014-mobile-setup-screens.md) (setup screens, onboarding, navigation).

Requires Node 22.13+ or 24.3+ (`.nvmrc` pins 24) and, for the API types,
[uv](https://docs.astral.sh/uv/). Run `uv sync --all-packages` once at the repo root.

## Everyday commands

Run these in `mobile/`.

```bash
npm start              # start Metro, the server that sends JavaScript to the phone
npm run typecheck      # tsc
npm run lint           # eslint
npm run format         # prettier (format:check only checks)
npm test               # jest
npm run api:generate   # after any backend API change: regenerate src/api/schema.d.ts
npm run api:check      # fails if the committed types are out of date (CI runs this)
```

## Layout

```
src/app/             Routes. Expo Router makes every file here a route, so tests go elsewhere.
  (auth)/            Sign-in and sign-up: only reachable when signed out
  (app)/             Signed in: onboarding (no income yet), or the tabs
    (tabs)/          Home, and Setup with its own stack of lists and forms
src/api/client.ts    The only HTTP code: base URL, auth header, refresh-and-retry, timeout, ApiError
src/api/session.ts   Tokens (refresh token in the Keychain, access token in memory) and refresh
src/api/schema.d.ts  Generated from the backend. Never edit by hand.
src/components/      Shared UI: form fields, date and select pickers, buttons, screen states
src/features/<name>/ Each feature's query hooks (api.ts), form and screens
src/lib/             Display and input conversion: formatCents, parseMoney, calendar dates
src/test/            Test helpers: a fake backend (refresh rotation, in-memory resources), a
                     fake Keychain, and helpers to launch the whole app or render hooks
```

**Money and dates in forms.** Amounts are typed as text and turned into cents by
`parseMoney`, which reads the digits and never uses a float. Due dates and deadlines stay
`"YYYY-MM-DD"` strings; never pass one to `new Date()`. Jest runs in America/Indiana, so a
date shown a day early fails a test.

**After a change.** Every setup mutation calls `invalidateAfterSetupChange`, which refetches
that resource and marks every `['planning', ...]` query stale. Plan and paycheck queries
(3D) must start with `['planning']`.

A feature's hook looks like `useQuery({ queryKey, queryFn: () => unwrap(api.GET('/path')) })`.
`unwrap` returns the typed data or throws an `ApiError` with the backend's `code` and `message`.

The app never does financial math. `PUT` must send the whole resource, with `null` for a
nullable field: the generated types require it, and a 422 names any field that is wrong.

## Reaching the backend from your iPhone

| Option                           | Setup                                           | Verdict                                                                                   |
| -------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Same Wi-Fi, PC's LAN address** | One firewall rule, once                         | **Use this.** Metro needs the same path anyway, it is fast, and there is no third party.  |
| Tunnel (cloudflared, ngrok)      | Install a tool, and the URL can change each run | Fallback for networks that block device-to-device traffic, such as guest or office Wi-Fi. |

You don't need to type the address. In development the app takes the host it loaded
JavaScript from and uses port 8000. The dev screen shows the address it is using.

**One-time setup, in PowerShell as Administrator, on your own home Wi-Fi only.** Windows
currently treats your Wi-Fi as _Public_, so the first command is needed for the rule to apply:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
New-NetFirewallRule -DisplayName "NextPay dev (API and Metro)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000,8081 -Profile Private
```

To undo the rule: `Remove-NetFirewallRule -DisplayName "NextPay dev (API and Metro)"`.

**Once per clone**, create the API's settings file. `.env` is git-ignored, and the API reads
it from the repo root wherever you start it. Without it, the API refuses to start and names
the missing settings.

```powershell
cd C:\Users\thead\Downloads\nextpay-phase0\nextpay
Copy-Item .env.example .env
```

**Each session**, start Docker Desktop, then open two terminals. Each one starts by changing
to the folder its command needs, so it doesn't matter where the terminal opens.

Terminal 1, the database, then the API. The migration step does nothing when the schema is
current, so it's safe every time, and it's required after pulling a new migration.
`--host 0.0.0.0` makes the API reachable from outside this PC:

```powershell
cd C:\Users\thead\Downloads\nextpay-phase0\nextpay
docker compose -f infra/docker-compose.yml up -d --wait
uv run alembic -c backend/alembic.ini upgrade head
uv run fastapi dev backend/app/main.py --host 0.0.0.0
```

Terminal 2, Metro:

```powershell
cd C:\Users\thead\Downloads\nextpay-phase0\nextpay\mobile
npm start
```

If your clone is somewhere else, change the paths: the API runs from the repo root, and
Metro runs from `mobile`.

### Troubleshooting

- **Metro shows `192.168.56.x`.** That is a VirtualBox adapter, which your phone can't reach.
  In terminal 2, in `mobile`, name your Wi-Fi address instead (find it with `ipconfig`):
  `$env:REACT_NATIVE_PACKAGER_HOSTNAME = "192.168.1.78"; npm start`
- **"Could not reach the server".** First check that the API answers in Safari on the phone at
  `http://<PC address>:8000/health`.
  - If Safari can't load it, the problem is the network: the firewall rule, the Wi-Fi being
    Public, the API running without `--host 0.0.0.0`, or the router isolating devices.
  - If Safari can load it, allow the app under Settings > Privacy & Security > Local Network.
- **A network that blocks device-to-device traffic.** Tunnel both sides. With the API
  running, start the tunnel in a third terminal (any folder):
  `cloudflared tunnel --url http://localhost:8000`. Then, in terminal 2, in `mobile`:
  `$env:EXPO_PUBLIC_API_URL = "https://<the-url>"; npx expo start --dev-client --tunnel`

## Your first iOS development build

A **development build** is your own copy of the app with a dev menu, signed for your phone.
EAS (Expo's cloud service) builds it, so you don't need a Mac. You rebuild only when native
code or config changes (a new native module, `app.json`). JavaScript changes reach the phone
instantly from Metro.

**Before you start**

- **A paid Apple Developer Program membership ($99/year).** Installing a build on a physical
  iPhone through EAS requires it; a free Apple ID won't work. Enrollment can take a day or two.
- A free [Expo account](https://expo.dev/signup).
- The bundle identifier in `app.json`, `com.theadedoyinmog.nextpay`, is what you want. It must
  be unique across Apple, and it's awkward to change after the first build.

**Steps**, in `mobile/`:

1. Sign in, and link the project. This adds a project ID to `app.json`. The project is already
   linked (`extra.eas.projectId`), so on this repo `init` only confirms the link. If `init`
   adds anything else to `app.json`, such as `extra.router`, remove it.
   ```powershell
   npx eas-cli@latest login
   npx eas-cli@latest init
   ```
2. Register your iPhone **before building**, because a build only runs on devices registered
   when it was made. Choose the website option, open the link on the iPhone, and install the
   profile it offers (Settings shows it under "Profile Downloaded").
   ```powershell
   npx eas-cli@latest device:create
   ```
3. Build. Sign in with your Apple account when asked, and let EAS create and manage the
   certificates. Free-plan builds wait in a queue, and the number per month is limited.
   ```powershell
   npx eas-cli@latest build --profile development --platform ios
   ```
4. Install. When the build finishes, open its link or QR code on the iPhone and tap Install.
5. Turn on Developer Mode, under Settings > Privacy & Security > Developer Mode. The iPhone
   restarts. The option appears only after a development build has been installed.
6. Start the API and Metro (see "Each session" above), then open NextPay. It should find your
   PC's Metro server; if not, enter the URL Metro prints. **Tap Allow** on the Local Network
   prompt.

**It worked if** the sign-in screen appears. Create an account, and the home screen shows
your email and, in development, the API address, status `ok` and an engine version.

To sign out on the phone, use **Log out** on the home screen. Signing in survives closing
the app, because the refresh token is kept in the iPhone's Keychain.
