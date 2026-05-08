---
title: "HLD: GOG Integration & Normalised Multi-Platform Library"
date: 2026-05-02
tags: [hld, gog, steam, library, multi-platform, ratings, hide, igdb]
story: "[[US-003: GOG Integration & Normalised Multi-Platform Library]]"
status: approved
---

## Overview

Extend SteamPunk's library pipeline to ingest the user's GOG collection alongside Steam, deduplicate shared titles using IGDB, surface cross-store availability, and add user-controlled rating and hide preferences.

## Goals & Non-Goals

**Goals**
- Authenticate with GOG and sync the user's owned game list
- Link Steam and GOG entries for the same game to a single canonical `games` row
- Show whether an owned-on-GOG game is purchasable on Steam, and vice versa
- Let the user rate (👍/👎) and hide any game in the unified library
- A toggle to surface hidden games

**Non-Goals**
- GOG achievements, wishlist, or playtime (GOG API does not expose reliable playtime)
- Other platforms (Epic, Xbox, PSN) — same architecture applies but out of scope here
- Price lookups for available-on-store games
- Scraping store pages; all availability data comes from IGDB

---

## Design

### 1. GOG Authentication

GOG does not offer a public OAuth2 client registration. The community has extracted working `client_id` / `client_secret` credentials from the GOG Galaxy desktop client. These are used to drive the standard OAuth2 authorization code flow at `https://auth.gog.com/auth`.

**Flow:**
1. User clicks "Connect GOG" on the Setup page
2. App opens `https://auth.gog.com/auth?client_id=...&redirect_uri=...&response_type=code` in the system browser
3. User approves; GOG redirects to `http://localhost:{port}/auth/gog/callback?code=...`
4. App exchanges `code` for `access_token` + `refresh_token` via POST to `https://auth.gog.com/token`
5. Tokens stored in `gandalf.json` under `gog.access_token` / `gog.refresh_token` / `gog.expires_at`

**Token refresh:** `collect.py` checks `expires_at` before each API call and refreshes proactively if within 60 seconds of expiry.

**Expired refresh token:** If the refresh request itself fails (e.g. the token has been revoked or the user hasn't synced in months), `collect.py` logs the error, skips the GOG sync entirely for that run, and sets a `gog.auth_expired = true` flag in `gandalf.json`. The Setup page reads this flag and displays a "Reconnect GOG" prompt. The flag is cleared on successful re-authentication.

**Credentials:** `GOG_CLIENT_ID` and `GOG_CLIENT_SECRET` stored in `gandalf.json`. The values are the community-extracted Galaxy app credentials (available publicly in reverse-engineering docs). This is a personal tool — no multi-tenant concerns.

### 2. GOG Library Sync

**Endpoint (unofficial):** `GET https://embed.gog.com/user/data/games` (returns list of GOG product IDs)  
**Enrichment:** `GET https://api.gog.com/products/{id}?expand=description` (title, cover, release date)

**Staging tables (new):**
```sql
stg_gog_library (
  product_id    VARCHAR PRIMARY KEY,
  title         VARCHAR,
  cover_url     VARCHAR,
  release_date  DATE,
  collected_at  TIMESTAMP
)
```

**Promote step** follows the same pattern as Steam: upsert into `platform_games` with `platform_id` = GOG's row in `platforms`. All GOG product IDs stored as `external_id`.

**Playtime:** GOG does not expose playtime via its web API. Playtime fields are left NULL for GOG entries and the playtime column is suppressed in the UI for GOG-only games.

**Rate limiting:** The GOG products API has no published rate limit. Apply a 0.5s delay between product enrichment requests (same cadence as the Steam app details fetch) as a conservative precaution.

### 3. Cross-Platform Game Matching via IGDB

IGDB (api.igdb.com) is a Twitch-operated database with broad Steam and GOG coverage. It exposes an `external_games` endpoint that maps IGDB game IDs to platform-specific IDs.

**Credentials:** Twitch Client ID + Client Secret → `gandalf.json` under `igdb.client_id` / `igdb.client_secret`. An app access token is obtained via Twitch OAuth client-credentials flow and cached with its TTL.

**Matching strategy (during promote):**

For each newly promoted `platform_game` with no `igdb_id` on its parent `games` row:
1. Query IGDB `external_games` for the platform-specific ID (Steam: `external_game_source=1`, GOG: `external_game_source=5`) → returns IGDB `game.id`
2. Check whether another `platform_game` already has that `igdb_id` linked
3. If yes: merge — point the new `platform_game.game_id` to the existing canonical `games` row
4. If no: set `games.igdb_id` on the existing row

**Match confidence:** Rather than accepting the first IGDB result, score candidates using all available signals — title similarity, publisher name, and release year — and only accept a match when the score clears a confidence threshold. Log near-misses (high-score but sub-threshold) for manual inspection. This guards against false positives on games with generic names or multi-entry series.

**Conflict rule:** If two platform entries would resolve to the same `igdb_id` but already point to different `games` rows, flag for manual review (log a warning, do not auto-merge). This avoids silent data loss on edge cases.

**Fallback:** If IGDB returns no confident match, leave `igdb_id` NULL. The game remains in the library as a platform-only entry. Games with `igdb_id = NULL` are silently skipped by the store availability pass — they will never receive availability badges until a match is found in a future sync.

### 4. Store Availability

**New table:**
```sql
store_availability (
  game_id       INTEGER REFERENCES games(id),
  platform_id   INTEGER REFERENCES platforms(id),
  available     BOOLEAN,
  external_id   VARCHAR,   -- platform-specific ID if available (e.g. Steam app_id)
  checked_at    TIMESTAMP,
  PRIMARY KEY (game_id, platform_id)
)
```

**Population strategy:**

For each canonical `games` row where the user owns it on Platform A but NOT Platform B:
1. Query IGDB `external_games` for Platform B's category to see if the game exists on that store
2. Write a `store_availability` row with `available = true/false` and `external_id` if found
3. `checked_at` is set to now

**Re-check cadence:** Store availability is only re-checked if `checked_at` is older than 7 days, or if the `igdb_id` was previously NULL and has now been resolved.

**Display:** `available` = true → show badge. `available` = false or no row → no badge.

### 5. Rating & Hide Preferences

Rather than adding columns to `library` (which models ownership+playtime), user preferences are stored in a dedicated table to keep concerns separate.

**New table:**
```sql
user_game_prefs (
  game_id       INTEGER REFERENCES games(id),
  rating        VARCHAR CHECK (rating IN ('up', 'down')),  -- NULL = no rating
  hidden        BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at    TIMESTAMP,
  PRIMARY KEY (game_id)
)
```

**Rating:** PUT `/library/games/{game_id}/rating` with body `{"rating": "up"|"down"|null}` — upserts the row.  
**Hide:** PUT `/library/games/{game_id}/hidden` with body `{"hidden": true|false}` — upserts the row.

Both endpoints return 200 with the updated preference state. UI updates optimistically.

**Cross-platform scope:** Preferences are intentionally keyed on `game_id` (the canonical game), not `platform_game_id`. Rating or hiding a game applies across all platforms you own it on — there is no per-platform preference.

**Show hidden toggle:** Client-side filter via a query param `?show_hidden=1`. The server includes hidden games in the response when the param is present, tagged with `"hidden": true` so the UI can render them visually distinct.

### 6. Schema Summary of New/Changed Objects

| Object | Change |
|---|---|
| `platforms` | New row: `GOG` (seeded at init) |
| `stg_gog_library` | New staging table |
| `games.igdb_id` | Already exists; populated by IGDB match step |
| `store_availability` | New table |
| `user_game_prefs` | New table (rating + hidden) |

### 7. Library Platform Filter

The library page exposes a platform filter that lets users narrow the view to one platform's games. The filter is populated data-driven from the `platforms` table, so every future integration gains a filter entry automatically — no UI code changes are required when a new platform is added.

**Endpoint contract:**

```
GET /library/games             → all games across enabled platforms
GET /library/games?platform=2  → games owned on platform_id 2 only
```

`platform` is optional; omitting it returns the full enabled-platform view.

**Filter chip population:** The client calls `GET /platforms?enabled=true` and renders one filter chip per row returned (ordered by `platforms.display_order` or alphabetically as a fallback). The currently active chip is highlighted; a preceding "All" chip returns to the unfiltered view.

**Multi-platform games:** A game owned on both Steam and GOG appears under both filter chips and in the "All" view. The canonical `games` row is returned once per query; the response includes a `platforms` array listing every platform the user owns it on.

**Disabled platforms:** Platforms toggled off in Connected Services ([[US-011: Connected Services Management]]) are excluded from `GET /platforms?enabled=true` and therefore absent from the filter. Their games are hidden from the library view while disabled.

**Adding a new platform:** Seed a row in `platforms` at init. The filter, the "All" aggregation, the pipeline sync loop, and the Connected Services list all read `platforms` at runtime — nothing else needs changing.

---

### 8. Sync Sequencing

```
collect.py run order:
1. Steam sync (existing)
2. GOG sync (new)
3. IGDB matching pass (runs after both platforms are staged)
4. Store availability pass (runs after IGDB matching)
```

Idempotency is preserved throughout — all steps use upserts. Rating and hidden flags are never overwritten by the pipeline.

---

## Data & Privacy Considerations

- GOG `access_token` and `refresh_token` stored only in `gandalf.json` (gitignored). Never in the database.
- `GOG_CLIENT_ID` / `GOG_CLIENT_SECRET` (community credentials) stored only in `gandalf.json`.
- `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` stored only in `gandalf.json`.
- `user_game_prefs` contains personal taste data — database file is gitignored.
- No GOG or IGDB data is committed to the repository.

---

## Open Questions

1. **Multi-user future:** `user_game_prefs` has no `user_id` column. Deferred — single-user experience for now. Add when multi-user blended preferences become a goal.
