---
title: "HLD: First-Run Setup Wizard"
date: 2026-05-03
tags: [hld, onboarding, setup, wizard, packaging, distribution]
story: "[[US-012: First-Run Setup Wizard]]"
status: draft
---

## Overview

Replace the implicit, crash-prone first-run experience with an explicit multi-step setup wizard. On first launch (no `gandalf.json`), the app initialises the secrets file with bundled and generated credentials, then walks the user through Steam setup (mandatory) and optional service connections (GOG, PSN, Nintendo Switch) entirely within the UI. Users never touch `gandalf.json` directly.

## Goals & Non-Goals

**Goals**
- Safely initialise `gandalf.json` on first launch before any route handler reads it
- Guide the user through Steam API key entry, Steam OpenID auth, and Steam session cookie in sequence
- Present optional service connections (GOG, PSN, Nintendo Switch) with the ability to skip each
- Enforce at least one service connected before wizard completion (Steam satisfies this alone)
- Trigger an initial sync and land the user in the library on completion
- Allow the wizard to be re-triggered from Connected Services settings (US-011)
- Introduce a centralised `save_secrets()` helper used by all credential-writing routes

**Non-Goals**
- Wizard progress persisted across app restarts (incomplete wizard = restart from step 1)
- Multi-user or account-switching setup
- Automating Steam API key generation (requires user to visit Steam website)

---

## Design

### 1. First-Run Initialisation

The app currently calls `load_secrets()` at module import time and crashes if `gandalf.json` is absent. This is fixed by an explicit init step that runs before the FastAPI app starts.

**`run.py` — updated launch sequence:**
```python
from src.init import ensure_gandalf_initialised
ensure_gandalf_initialised()   # creates gandalf.json if absent

uvicorn.run("main:app", ...)
```

**`src/init.py` — `ensure_gandalf_initialised()`:**
1. Check if `gandalf.json` exists
2. If not, write a fresh file with:
   - Bundled credentials (IGDB, GOG client_id/secret) — loaded from a constants module compiled into the exe
   - Generated `app.session_secret` (random 32-byte hex)
   - Empty user credential sections (`steam: {}`, `psn: {}`, `switch: {}`)
3. If the file already exists, leave it untouched

**Bundled credentials source:** A `src/bundled_credentials.py` file (gitignored, injected at build time) that exposes constants:
```python
IGDB_CLIENT_ID     = "..."
IGDB_CLIENT_SECRET = "..."
GOG_CLIENT_ID      = "..."
GOG_CLIENT_SECRET  = "..."
```
This file is never committed. During development, a `bundled_credentials.example.py` with placeholder values is committed instead. The build process substitutes the real values.

### 2. Centralised `save_secrets()` Helper

A `save_secrets(updates: dict)` function is added to `src/db.py` using a deep-merge strategy so callers only specify the keys they're changing:

```python
def save_secrets(updates: dict) -> None:
    data = load_secrets()
    _deep_merge(data, updates)
    with open(SECRETS_PATH, "w") as f:
        json.dump(data, f, indent=2)
```

All existing credential-writing routes (`/setup`, `/auth/gog/connect`, `/auth/psn/connect`, `/preferences`, etc.) are refactored to use this helper, eliminating the repeated read-modify-write pattern.

### 3. First-Run Detection & Wizard Gate

**Detection logic** (evaluated on every request via middleware):
- `gandalf.json` exists but `steam.api_key` is absent or empty → first-run state
- User is not authenticated (no session) → also redirect to wizard start

**Middleware behaviour:**
- Requests to `/wizard/*` are always allowed through
- Requests to `/auth/steam` and `/auth/callback` are always allowed (needed mid-wizard)
- All other requests while in first-run state redirect to `GET /wizard/steam-api`
- Once Steam is fully configured and the user is authenticated, the gate is lifted

### 4. Wizard Route Structure

```
GET  /wizard/steam-api          Step 1 — Steam API key + vanity URL entry
POST /wizard/steam-api          Validate and save; redirect to Steam OpenID
GET  /auth/steam                (existing) — Steam OpenID redirect
GET  /auth/callback             (existing, modified) — on success, redirect to /wizard/steam-cookie
GET  /wizard/steam-cookie       Step 2 — Steam session cookie instructions
POST /wizard/steam-cookie       Validate and save; redirect to /wizard/services
GET  /wizard/services           Step 3 — Optional service connections (GOG, PSN, Switch)
POST /wizard/complete           Final step — trigger sync, redirect to /library
```

**Progress indicator:** A simple step bar (1 / 2 / 3) rendered in the wizard layout showing Steam API → Steam Login → Services.

### 5. Step Detail

#### Step 1 — Steam API Key (`/wizard/steam-api`)

**Fields collected:**
- Steam API key (paste from `https://steamcommunity.com/dev/apikey`)
- Steam vanity URL or Steam ID64

**Validation (`POST /wizard/steam-api`):**
1. Call `https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={key}&vanityurl={vanity}` to confirm the key is valid and resolve `steam_id64`
2. On success: `save_secrets({"steam": {"api_key": key, "vanity_id": vanity, "steam_id64": resolved_id}})`
3. Redirect to `/auth/steam` (Steam OpenID flow)
4. On failure: re-render the form with an inline error

**UI:** Two labelled input fields, a "How to get your API key" expandable section with a direct link to the Steam developer portal, and a "Continue" button.

#### Step 2 — Steam Session Cookie (`/wizard/steam-cookie`)

**Identical to the existing Steam tab in `/setup`** — same 5-step DevTools instructions, same `POST` handler logic. The only change is context: the handler redirects to `/wizard/services` on success instead of `/library`.

#### Step 3 — Optional Services (`/wizard/services`)

A single page showing cards for GOG, PSN, and Nintendo Switch, each with:
- A brief one-line description of what connecting this service adds
- A "Connect" button that launches the existing platform auth flow
- A "Skip for now" link

**Connection flows reuse existing routes** (`/auth/gog`, `/auth/psn/connect`, etc.) with a `?from=wizard` query parameter that causes the success redirect to return to `/wizard/services` rather than `/setup`.

**"Finish Setup" button** is always visible. It posts to `POST /wizard/complete`.

#### Completion (`POST /wizard/complete`)

1. Verify at least one service is connected (Steam session cookie present — Steam alone qualifies)
2. Trigger a background sync (`_run_sync()`) for all connected platforms
3. Redirect to `/library`

### 6. Re-triggering the Wizard

A "Re-run Setup Wizard" option is added to the Connected Services section in `/preferences` (US-011). It clears only the wizard-completion marker (not credentials) and redirects to `/wizard/steam-api`. Since existing credentials are pre-populated in the form fields, re-running is fast for users who just want to add a new service.

### 7. Modified `/auth/callback` Behaviour

Currently: after successful Steam auth, redirects to `/setup` if no session cookie, else `/library`.

Updated:
- If in wizard flow (no `steam.api_key` configured, or `?wizard=1` session flag): redirect to `/wizard/steam-cookie`
- If session cookie already present (re-auth or reconnect): redirect to `/library`
- Else: redirect to `/wizard/steam-cookie` (existing first-run case)

### 8. Schema Summary — No DB Changes

All changes are in `gandalf.json` structure, route handlers, and templates. No database schema changes required.

### 9. `gandalf.json` First-Run Initial State

```json
{
  "steam":  {},
  "gog":    { "client_id": "<bundled>", "client_secret": "<bundled>" },
  "psn":    {},
  "switch": {},
  "igdb":   { "client_id": "<bundled>", "client_secret": "<bundled>" },
  "app":    { "session_secret": "<generated>", "timezone": "UTC" }
}
```

---

## Data & Privacy Considerations

- `bundled_credentials.py` is gitignored and injected at build time. It must never be committed.
- `bundled_credentials.example.py` with placeholder values is committed so developers can run the app locally without the real credentials.
- `app.session_secret` is generated fresh per installation — each user's session is isolated.
- No user credentials are collected before the user explicitly enters them in the wizard.

---

## Open Questions

1. **Steam API key UX:** The open question from the story — can we automate key generation? No: Steam requires the user to visit their developer portal and accept terms. The wizard can link directly to the page and explain the steps, but cannot automate the registration itself.
	1. This isn't a question then
2. **`bundled_credentials.py` build injection:** The mechanism for substituting real credentials at build time (e.g. environment variables read by a build script, or a secrets manager) is not defined here — to be resolved when the packaging story is written.
	1. This isn't an open question then
