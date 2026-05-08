---
title: "HLD: Steam Auth & Library Viewer"
date: 2026-05-01
tags: [hld, steam, auth, library, web-app]
story: "[[US-001: Steam Auth & Library Viewer]]"
status: draft
---

## Overview

A locally-hosted FastAPI web application that authenticates the user via Steam OpenID 2.0 and presents their game library in a browsable interface. This is the foundation layer — it handles auth, session management, data collection, and the UI shell that US-002 (agent) builds on top of.

---

## Goals & Non-Goals

**Goals**
- Secure Steam login without handling credentials
- Signed server-side sessions
- Enriched game library persisted locally
- Clean browsable UI: games list + user profile
- Shared navigation shell for all future pages

**Non-Goals**
- Agent / recommendations (US-002)
- Friends / social data
- Any write operations to Steam

---

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | FastAPI | Async, modern Python, minimal attack surface |
| Templates | Jinja2 | Built into Starlette/FastAPI, no build step |
| Interactivity | HTMX | Dynamic updates + chat streaming without a JS framework |
| Styling | TailwindCSS (CDN) | No build tooling, polished output |
| Auth | Steam OpenID 2.0 via `python-openid` | Standard, no third-party auth vendor |
| Sessions | Starlette signed cookie sessions | Server-side, secret key stored in `gandalf.json` |
| Database | DuckDB 1.5.1 | File-based, no server, excellent for analytical queries (preference aggregations) |

---

## Architecture

```
Browser
  │  GET /
  │  (unauthenticated → redirect)
  ▼
┌──────────────────────────────────┐
│  FastAPI App  (main.py)          │
│                                  │
│  /                → login page   │
│  /auth/steam      → OpenID init  │
│  /auth/callback   → OpenID return│
│  /logout          → clear session│
│  /library         → games list   │
│  /profile         → user profile │
└───────────┬──────────────────────┘
            │ reads
            ▼
┌──────────────────────────────────┐
│  Data Layer                      │
│                                  │
│  steampunk.duckdb  (root)        │
│  stg_* tables  → raw per source  │
│  canonical tables → normalised   │
└───────────┬──────────────────────┘
            │ written by
            ▼
┌──────────────────────────────────┐
│  Data Pipeline  (src/collect.py) │
│                                  │
│  Steam Web API                   │
│  Steam Store API                 │
│  Wishlist / Achievements         │
└──────────────────────────────────┘
```

---

## Steam OpenID 2.0 Auth Flow

```
1. User visits /
2. App redirects to /auth/steam
3. App builds OpenID request → redirects browser to Steam login page
4. User authenticates on Steam's servers (app never sees credentials)
5. Steam redirects browser back to /auth/callback with signed assertion
6. App verifies assertion with python-openid (validates against Steam's endpoint)
7. App extracts SteamID64 from verified identity URL
8. App creates signed session cookie containing SteamID64
9. User is redirected to /library
```

Session secret key is stored in `gandalf.json` as `app.session_secret`. Never hardcoded.

---

## Routes

| Route | Auth required | Description |
|---|---|---|
| `GET /` | No | Login page with "Sign in through Steam" button |
| `GET /auth/steam` | No | Initiates OpenID redirect to Steam |
| `GET /auth/callback` | No | Handles Steam's return, creates session |
| `GET /logout` | Yes | Clears session, redirects to `/` |
| `GET /library` | Yes | Paginated games list with search/filter |
| `GET /profile` | Yes | User profile + library stats |

All authenticated routes share a common base template with the top-right navigation dropdown.

---

## UI Layout

### Login page (`/`)
- Centred card with Steam logo and "Sign in through Steam" button (official Steam badge)
- No username/password fields — auth is fully delegated to Steam

### Navigation dropdown (all authenticated pages)
- Top-right: Steam avatar thumbnail + display name
- Dropdown items: **Games List**, **User Profile**, **Logout**
- Implemented as a Tailwind disclosure component, toggled by HTMX

### Games List (`/library`)
- Search bar (filters by game name, tag, or genre client-side via HTMX)
- Game cards: thumbnail, name, playtime, top 3 tags
- Never-launched games shown with a muted style
- Sortable by: playtime (desc default), name, achievement %

### User Profile (`/profile`)
- Steam avatar (large), display name
- Stats summary: total games owned, total hours played, top 5 genres by weighted playtime

---

## Data Pipeline Detail

See [HLD-002](HLD-002-Steam-Game-Preference-Agent.md) for full pipeline spec. For US-001 the pipeline runs as a one-time setup step:

```bash
python src/collect.py
```

This populates the `stg_steam_*` staging tables and promotes data into the canonical tables. The app queries `steampunk.duckdb` at runtime — it does not call Steam APIs on every page load.

---

## Data & Privacy Considerations

- Session cookie is signed with `app.session_secret` from `gandalf.json` — tamper-evident
- `steampunk.duckdb` is gitignored — library data never committed
- `gandalf.json` is gitignored — secrets never committed
- OpenID verification is performed server-side against Steam's endpoint — assertion cannot be forged
- App binds to `127.0.0.1` only — not accessible outside localhost

---

## Folder Structure

```
SteamPunk/
├── gandalf.json               # secrets (gitignored)
├── steampunk.duckdb           # database (gitignored)
├── src/
│   ├── schema.sql             # DDL — stg_* + canonical tables
│   ├── main.py                # FastAPI app factory + patchable state
│   ├── shared.py              # shared state: secrets, templates, get_db helpers
│   ├── auth.py                # Steam OpenID logic
│   ├── db.py                  # DuckDB connection + helpers
│   ├── collect.py             # data pipeline entry point (shim → collectors/)
│   ├── collectors/            # per-platform pipeline modules
│   │   ├── steam.py, gog.py, psn.py, xbox.py, switch.py
│   │   ├── igdb.py            # IGDB matching + store availability
│   │   └── pipeline.py        # shared constants + merge helpers
│   ├── routers/               # FastAPI route handlers
│   │   ├── auth.py, library.py, sync.py, setup.py
│   ├── profile.py             # preference profile builder (US-002)
│   └── agent.py               # Claude agent (US-002)
├── templates/
│   ├── base.html              # shared layout + nav dropdown
│   ├── login.html
│   ├── library.html
│   └── profile.html
├── static/
│   └── (any local static assets)
└── SteamPunkVault/
```

---

## Decisions

- **Pipeline on first login** — if the DB is empty on first login, the pipeline runs automatically before the library page loads.
- **Pagination** — none. Full library loaded in one DuckDB query; client-side filtering via HTMX. Revisit only if library exceeds ~2000 games.
- **Data freshness** — no staleness warning. The UI shows a "Last synced: [date/time]" indicator (sourced from `MAX(collected_at)` on `stg_steam_library`) with a **Sync Now** button that re-runs the pipeline on demand.
