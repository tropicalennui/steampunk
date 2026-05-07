---
title: "HLD: Steam Game Preference Agent"
date: 2026-05-01
tags: [hld, steam, recommendations, agent]
story: "[[US-002: Steam Game Preference Agent]]"
depends-on: "[[HLD-001: Steam Auth & Library Viewer]]"
status: draft
---

## Overview

A Python-based pipeline that pulls a user's Steam library and enriches it with store metadata, then builds a structured preference profile. A Claude agent reads that profile and uses it to recommend games the user doesn't yet own.

Two distinct phases:
1. **Data pipeline** — collect, enrich, and persist Steam data locally
2. **Agent** — consume the persisted profile and answer recommendation queries

---

## Goals & Non-Goals

**Goals**
- Collect all owned games with playtime, achievement rate, wishlist status, and review sentiment
- Enrich each game with Steam Store tags and genres
- Produce a preference profile that is human-readable and agent-consumable
- Recommend games not yet owned with ranked scores and reasoning

**Non-Goals**
- Real-time data (pipeline runs on demand, data is cached)
- Friends/social signals
- Purchase / price integration
- Any write operations back to Steam

---

## Architecture

```
gandalf.json
  └─ steam.api_key
  └─ steam.user_id
        │
        ▼
┌─────────────────────┐
│   Data Pipeline     │  (collect.py)
│                     │
│  Steam Web API      │──► owned games + playtime
│  Steam Store API    │──► tags, genres, categories per game
│  Wishlist endpoint  │──► wishlist game IDs
│  Achievements API   │──► completion % per game
│  Reviews endpoint   │──► user's written reviews
└────────┬────────────┘
         │ writes
         ▼
┌─────────────────────┐
│   Data Layer        │  (data/)
│                     │
│  library.json       │  enriched game records
│  profile.json       │  distilled preference profile
└────────┬────────────┘
         │ reads
         ▼
┌─────────────────────┐
│   Agent             │  (agent.py)
│                     │
│  Claude (Sonnet)    │──► tool: read_profile()
│  System prompt      │──► tool: search_steam_store()
│  built from         │──► tool: get_game_details()
│  profile.json       │
└─────────────────────┘
```

---

## Data Pipeline Detail

### Steam API Endpoints Used

| Data | Endpoint |
|---|---|
| Owned games + playtime | `IPlayerService/GetOwnedGames` |
| Recent activity | `IPlayerService/GetRecentlyPlayedGames` |
| Achievement stats | `ISteamUserStats/GetPlayerAchievements` (per game) |
| Store metadata | `store.steampowered.com/api/appdetails?appids={id}` |
| Wishlist | `store.steampowered.com/wishlist/profiles/{id}/wishlistdata/` |
| User reviews | `store.steampowered.com/appreviews/{appid}?filter=mine` |

### Enriched Game Record (`library.json`)

Each entry in `library.json` represents one owned game:

```json
{
  "app_id": 12345,
  "name": "Game Name",
  "playtime_hours": 42.5,
  "last_played": "2025-03-10",
  "never_launched": false,
  "achievement_completion_pct": 68,
  "on_wishlist": false,
  "user_review": "Great atmosphere, loved the pacing.",
  "genres": ["RPG", "Adventure"],
  "tags": ["Open World", "Story Rich", "Dark Fantasy", "Singleplayer"],
  "categories": ["Single-player", "Steam Achievements"],
  "content_descriptors": []
}
```

`content_descriptors` is used to filter explicit content at collection time — games with adult descriptor flags are excluded from the profile and recommendations by default.

### Rate Limiting
- Store `appdetails` endpoint: ~200 requests/minute safe limit
- Achievement endpoint: one call per game — run with a small delay between calls
- Library data is cached locally; pipeline skips re-fetching unless `--refresh` flag passed

---

## Preference Profile (`profile.json`)

The profile distils the raw library into ranked signals for the agent.

```json
{
  "generated_at": "2026-05-01T00:00:00Z",
  "total_owned": 312,
  "total_played": 187,
  "total_never_launched": 125,
  "top_genres": [
    { "name": "RPG", "weighted_hours": 340, "game_count": 28 }
  ],
  "top_tags": [
    { "name": "Story Rich", "weighted_hours": 510, "game_count": 45 }
  ],
  "negative_signals": {
    "never_launched_genres": ["Sports", "Racing"],
    "never_launched_tags": ["Multiplayer", "Battle Royale"]
  },
  "high_engagement_games": [
    { "name": "Game A", "playtime_hours": 200, "achievement_pct": 100 }
  ],
  "wishlist_tags": ["Metroidvania", "Pixel Art"],
  "review_sentiment_summary": "User strongly prefers narrative-driven singleplayer games with atmospheric world-building. Consistently negative about games with heavy grinding."
}
```

Tag/genre weights are calculated as: `playtime_hours * engagement_multiplier`, where `engagement_multiplier = 1 + (achievement_completion_pct / 100)`. This means a game played for 50 hours with 100% achievements outweighs one played for 80 hours with 0% achievements.

---

## Agent Design

The agent is a Claude session with:
- A **system prompt** that injects the full `profile.json` as context
- Three tools available during conversation:

| Tool | Purpose |
|---|---|
| `read_profile()` | Returns the current preference profile |
| `search_steam_store(tags, genres, exclude_ids, max_price?)` | Searches Steam for games matching tags/genres; `max_price` is optional USD value |
| `get_game_details(app_id)` | Fetches full store metadata including current price for a specific game |

### Recommendation Flow

1. User asks for recommendations
2. Agent reads profile → extracts top tags/genres + negative signals
3. Agent calls `search_steam_store` with positive tag set, excluding owned game IDs
4. Agent calls `get_game_details` on candidates to verify fit
5. Agent ranks results and writes a short explanation per recommendation

---

## Data & Privacy Considerations

- `library.json` and `profile.json` are stored in `data/` which is gitignored — they contain personal play history
- `gandalf.json` holds the API key and Steam user ID — already gitignored
- No data is sent to any third party beyond Valve's own API
- User reviews fetched are the user's own public Steam reviews

---

## Folder Structure

```
SteamPunk/
├── gandalf.json          # secrets (gitignored)
├── data/                 # generated data (gitignored)
│   ├── library.json
│   └── profile.json
├── src/
│   ├── collect.py        # data pipeline entry point (shim → collectors/)
│   ├── collectors/       # per-platform pipeline modules
│   ├── profile.py        # profile builder
│   └── agent.py          # Claude agent + tools
└── SteamPunkVault/
    └── ...
```

---

## Open Questions

- [ ] How many games are in the library? Will determine whether we need async fetching for the enrichment step.
- [ ] `profile.json` is persisted per user account and rebuilt when `collect.py --refresh` is run; should a staleness threshold trigger an automatic refresh prompt?
- [ ] What model for the agent? Sonnet 4.6 is the default; consider Opus if recommendation reasoning quality needs improving.
- [ ] Should recommendation results be persisted, or always generated fresh?
