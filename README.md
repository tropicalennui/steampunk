# SteamPunk

A personal gaming library aggregator and AI recommendation engine. SteamPunk pulls your game libraries from Steam, GOG, PlayStation Network, and Nintendo Switch into a single normalized database, then (in future versions) uses Claude AI to surface personalized recommendations based on your actual play history.

## Features

- **Unified library** — games from Steam, GOG, PSN, and Nintendo Switch in one place
- **Preference profile** — automatically derived from playtime, genres, tags, achievements, and ratings
- **AI agent** — conversational game recommendations via Claude, with filtering by price, genre, platform, and more
- **Sync pipeline** — refresh any or all platforms on demand; inspect detailed logs
- **Setup wizard** — guided first-run flow to connect each platform

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Database | DuckDB (embedded) |
| AI | Anthropic Claude API |
| Templating | Jinja2 |
| HTTP clients | httpx, requests |

## Prerequisites

- Python 3.11+
- API credentials for any platforms you want to connect (see [Setup](#setup))

## Installation

```bash
git clone https://github.com/<your-username>/SteamPunk.git
cd SteamPunk
pip install -r requirements.txt
```

## Setup

Create `gandalf.json` in the project root with your credentials:

```json
{
  "SESSION_SECRET": "<random-secret>",
  "STEAM_API_KEY": "<your-steam-api-key>",
  "ANTHROPIC_API_KEY": "<your-anthropic-api-key>"
}
```

Additional platform credentials (GOG OAuth tokens, PSN NPSSO, Nintendo Switch auth) are stored in the same file after you authenticate through the app's setup wizard.

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
| Nintendo Switch | Account auth flow |

Instructions for obtaining each credential are in the in-app setup wizard and the [User Guides](SteamPunkVault/User-Guides/).

## Project Structure

```
src/
  main.py       # FastAPI app and all HTTP endpoints
  collect.py    # Data pipeline (fetches and normalizes games from all platforms)
  schema.sql    # DuckDB schema
  auth.py       # OAuth/session helpers
  db.py         # Database initialization
  init.py       # Startup / secrets loading
SteamPunkVault/ # Obsidian knowledge base (stories, designs, guides)
run.py          # Entry point
```

## License

Personal project — not licensed for redistribution.
