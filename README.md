# SteamPunk

A personal gaming library aggregator. SteamPunk pulls your game libraries from Steam, GOG, PlayStation Network, Nintendo Switch, and Xbox Live into a single normalized database.

## Features

- **Unified library** — games from Steam, GOG, PSN, Nintendo Switch, and Xbox Live in one place
- **Sync pipeline** — refresh any or all platforms on demand; granular sub-syncs (e.g. Steam › Achievements only); inspect streaming logs
- **Setup wizard** — guided first-run flow to connect each platform
- **IGDB metadata** — game summaries, developers, publishers, first release dates, and aggregate ratings sourced from IGDB and shown on each game's detail page
- **Achievement & trophy detail** — per-achievement icon grids with unlock dates for Steam; completion percentages and gamerscore across all platforms
- **Store availability** — flags games you own on one platform that are also available on another

## Planned

- **Preference profile** — automatically derived from playtime, genres, tags, achievements, and ratings
- **AI agent** — conversational game recommendations via Claude

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Database | DuckDB (embedded) |
| AI | Anthropic Claude API |
| Templating | Jinja2 |
| HTTP clients | httpx, requests |

## Prerequisites

- Python 3.12+
- API credentials for any platforms you want to connect (see [Setup](#setup))

## Installation

```bash
git clone https://github.com/<your-username>/SteamPunk.git
cd SteamPunk
pip install -r requirements.txt
```

## Setup

The first-run setup wizard will prompt for your Steam API key and walk you through connecting any other platforms. Credentials are stored in `gandalf.json` at the project root (gitignored).

If you need to pre-populate `gandalf.json` manually, the minimum required structure is:

```json
{
  "app": { "session_secret": "<random-string>" },
  "steam": { "api_key": "<your-steam-api-key>" }
}
```

Additional platform credentials (GOG OAuth tokens, PSN NPSSO, Nintendo Switch session token, Xbox Live auth) are added automatically when you authenticate through the setup wizard.

> **Security note:** `gandalf.json` is gitignored and must never be committed.

## Running

```bash
python run.py
```

The app starts at `http://localhost:8000`. Open it in a browser and follow the first-run setup wizard to connect your gaming platforms.

## Platform Integrations

| Platform | Auth method |
|---|---|
| Steam | API key + session cookie |
| GOG | OAuth 2.0 |
| PlayStation Network | NPSSO token |
| Nintendo Switch | Session token (PKCE flow) |
| Xbox Live | OAuth 2.0 |

Instructions for obtaining each credential are in the in-app setup wizard and the [User Guides](SteamPunkVault/User-Guides/).

## Project Structure

```
src/
  main.py           # FastAPI app factory + shared state
  shared.py         # secrets, templates, DB helpers
  auth.py           # Steam OpenID helpers
  db.py             # DuckDB connection + secrets I/O
  init.py           # First-run secrets initialisation
  schema.sql        # DuckDB schema
  collect.py        # Pipeline entry point (CLI shim)
  collectors/       # Per-platform data pipeline
    steam.py, gog.py, psn.py, switch.py, xbox.py
    igdb.py         # IGDB matching, metadata enrichment + store availability
    pipeline.py     # Shared constants + merge helpers
  routers/          # FastAPI route handlers
    auth.py         # All /auth/* routes
    library.py      # Library view, API, merge
    sync.py         # Sync trigger + log viewer
    setup.py        # Setup page + wizard
SteamPunkVault/     # Obsidian knowledge base (designs, guides)
tests/              # pytest suite
run.py              # Entry point
```

## License

Personal project — not licensed for redistribution.
