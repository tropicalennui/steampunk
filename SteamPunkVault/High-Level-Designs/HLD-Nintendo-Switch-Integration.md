---
title: "HLD: Nintendo Switch Integration"
date: 2026-05-03
tags: [hld, nintendo, switch, library, multi-platform]
story: "[[US-010: Nintendo Switch Integration]]"
status: draft
---

## Overview

Extend the multi-platform library pipeline to ingest the user's Nintendo Switch game library and playtime data alongside Steam, GOG, and PSN. Switch entries are deduplicated against existing titles via IGDB and merged into the canonical `games` table. Playtime feeds the preference agent as an engagement signal. Authentication uses Nintendo's unofficial OAuth + f-token flow, with the `nxapi` Node.js project as the reference implementation and the community `imink` API for f-token generation.

## Goals & Non-Goals

**Goals**
- Authenticate with Nintendo Account using the unofficial OAuth + f-token flow and persist the session token in `gandalf.json`
- Sync the user's Switch game library and playtime into `stg_switch_library`
- Promote staged games into `platform_games` under a `Nintendo Switch` platform row
- Sync per-game playtime (total minutes, first played, last played) as preference-agent signals
- Link Switch titles to canonical `games` rows via IGDB matching
- Surface cross-platform store availability badges for Switch-owned games

**Non-Goals**
- Nintendo eShop price lookups
- Wish list or download list (unowned) data
- Friend activity or social features
- Individual game achievement / stamp detail — playtime summary only
- Game-specific API data (SplatNet, NookLink, etc.)

---

## Design

### 1. Nintendo Switch Authentication

Nintendo does not offer a public API. The community has reverse-engineered the Nintendo Switch Online (NSO) mobile app authentication flow. The reference implementation is `nxapi` (TypeScript/Node.js by samuelthomas2774). This HLD implements the equivalent flow directly in Python rather than depending on `nso-api`, which was archived January 2026.

F-token generation — the cryptographic step that makes requests appear to originate from the official NSO app — is handled by the community `imink` API (`https://api.imink.app/f`).

**Flow:**
1. App generates a Nintendo Account authorization URL (with a random `state` and `code_verifier` stored in `gandalf.json`)
2. User opens the URL in their browser and logs into their Nintendo Account
3. Nintendo redirects to `npf71b963c1b7b6d119://auth#...` — a custom protocol the browser cannot open; the page appears to fail or hang
4. User copies the full redirect URL from the browser's address bar and pastes it into the SteamPunk Setup page
5. App extracts the `session_token_code` from the URL and POSTs it to Nintendo's `/connect/1.0.0/api/session_token` to obtain a `session_token`
6. `session_token` stored in `gandalf.json` under `switch.session_token`; `state` and `code_verifier` are discarded

**Token hierarchy (not all stored):**

| Token | Validity | Stored |
|---|---|---|
| `session_token` | ~2 years | Yes — `gandalf.json` |
| `id_token` / Coral access token | 15 min | No — derived at runtime |
| Web service token | 2 hours | No — derived at runtime |

Because the `session_token` is valid for approximately two years, re-authentication is rarely needed. Runtime tokens (`id_token`, Coral access token) are derived from the `session_token` on each sync run via the imink f-token flow and discarded afterward.

**imink API call:**
- `POST https://api.imink.app/f` with `{ "token": <id_token>, "hash_method": 1 }`
- Returns the `f` parameter required by Nintendo's `/v1/Account/Login`
- Rate limit: ~10–20 requests per hour per user (well within a single sync run)

**Token expiry handling:** If the `session_token` is rejected (revoked or expired), `collect.py` logs the error, skips the Switch sync for that run, and sets `switch.auth_expired = true` in `gandalf.json`. The Setup page reads this flag and displays a "Reconnect Nintendo" prompt. The flag is cleared on successful re-authentication.

**Credentials stored in `gandalf.json`:**
```json
{
  "switch": {
    "session_token": "...",
    "auth_expired": false
  }
}
```

**ToS note:** This flow uses an unofficial API that violates Nintendo's Terms of Service. The community infrastructure (`nxapi`, `imink`) has been stable since ~2019 and Nintendo has not actively shut it down. Risk of account action is low at personal-use request rates. Conservative rate limiting (see §2) is applied regardless.

### 2. Switch Library & Playtime Sync

**Authentication sequence (per sync run):**
1. Load `switch.session_token` from `gandalf.json`
2. POST to `/connect/1.0.0/api/token` with session token → receive `id_token`
3. POST `id_token` to `imink` → receive `f` parameter
4. POST to `/v1/Account/Login` with `f` and `id_token` → receive Coral access token
5. POST Coral token to imink (hash method 2) → receive second `f` for web service
6. POST to `/v1/Game/GetWebServiceToken` → receive web service access token
7. Use web service token for library and activity requests

**Library endpoint:** `GET /v1/Game/ListWebServices` — returns the user's game list with title names and Nintendo unique IDs (`nsUid`).

**Play activity endpoint:** Nintendo exposes play history through the Switch activity log via the NSO app API. Each game entry includes:
- `totalPlayedMinutes` — aggregate playtime
- `firstPlayedAt` — timestamp of first session
- `lastPlayedAt` — timestamp of most recent session

**Staging table (new):**
```sql
stg_switch_library (
  ns_uid              VARCHAR PRIMARY KEY,
  title               VARCHAR,
  play_time_mins      INTEGER,         -- NULL if no play recorded
  first_played_at     TIMESTAMP,       -- NULL if unavailable
  last_played_at      TIMESTAMP,       -- NULL if unavailable
  collected_at        TIMESTAMP
)
```

**Rate limiting:** Apply a 0.5 s delay between paginated requests. The imink API imposes its own rate limit; a single sync run makes at most 2 imink calls (one per hash method) regardless of library size.

**Promote step:** Upsert from `stg_switch_library` into `platform_games` using `ns_uid` as `external_id`. The `Nintendo Switch` row in `platforms` is the `platform_id`. `play_time_mins`, `first_played_at`, and `last_played_at` are written to dedicated columns on `platform_games` (see §5).

### 3. Cross-Platform Game Matching via IGDB

Switch titles are matched to canonical `games` rows using the same IGDB `external_games` strategy established in HLD-GOG-Integration-And-Normalised-Library.

**IGDB category for Nintendo Switch:** `category = 8` (Nintendo Switch eShop). Verify against IGDB API docs during implementation — fall back to title-similarity matching if the category lookup yields no result.

**Matching strategy:** Identical to HLD-GOG §3 — score candidates on title similarity + publisher + release year, accept only above the confidence threshold, log near-misses, flag conflicts for manual review rather than auto-merging.

**Fallback:** If no confident IGDB match is found, leave `igdb_id` NULL. The game remains as a Switch-only entry and is silently skipped by the store availability pass until a future sync resolves the match.

### 4. Store Availability

No changes to the `store_availability` table or population strategy from HLD-GOG §4. Switch-owned games with a resolved `igdb_id` will automatically be evaluated for Steam and GOG availability on the next availability pass.

### 5. Schema Changes

**`platform_games` — new columns:**
```sql
ALTER TABLE platform_games ADD COLUMN play_time_mins INTEGER;
ALTER TABLE platform_games ADD COLUMN first_played_at TIMESTAMP;
ALTER TABLE platform_games ADD COLUMN last_played_at  TIMESTAMP;
```

These columns are `NULL` for existing Steam, GOG, and PSN rows unless backfilled. Steam playtime data (already stored in a different column) will be migrated to `play_time_mins` as part of this migration for consistency. PSN stores `trophy_progress` only — no playtime available from that platform.

**New staging table:** `stg_switch_library` (defined in §2 above).

**New `platforms` row:** `Nintendo Switch` (seeded at init alongside existing platforms).

### 6. Schema Summary of New/Changed Objects

| Object | Change |
|---|---|
| `platforms` | New row: `Nintendo Switch` (seeded at init) |
| `stg_switch_library` | New staging table |
| `platform_games.play_time_mins` | New column — total playtime in minutes |
| `platform_games.first_played_at` | New column — first session timestamp |
| `platform_games.last_played_at` | New column — most recent session timestamp |

### 7. Sync Sequencing

```
collect.py run order:
1. Steam sync (existing)
2. GOG sync (existing)
3. PSN sync (existing)
4. Switch sync (new)
5. IGDB matching pass (runs after all platforms are staged)
6. Store availability pass (runs after IGDB matching)
```

Idempotency is preserved throughout — all steps use upserts. Playtime columns are overwritten on each sync (they reflect current Nintendo state). User preferences (`user_game_prefs`) are never touched by the pipeline.

### 8. Preference Agent Integration

Switch playtime is surfaced to the preference agent as an engagement signal alongside Steam playtime and PSN trophy completion:

- Switch games in the owned-games list with a Nintendo Switch platform tag
- `play_time_mins` as engagement depth (analogous to Steam playtime)
- `last_played_at` as recency signal
- Games with `play_time_mins = NULL` or zero are included in the library but flagged as low-signal — they are prioritised candidates for the preference quiz (US-009)

---

## Data & Privacy Considerations

- `switch.session_token` stored only in `gandalf.json` (gitignored). Never in the database or any committed file.
- Runtime tokens (`id_token`, Coral access token, web service token) are never persisted — derived at sync time and discarded.
- `stg_switch_library` and `platform_games` contain game title data only — no Nintendo Account identifiers or PII beyond the game list.
- The `imink` third-party service receives only the `id_token` (which is scoped to this app's session); it does not receive the `session_token` or any account credentials.
- The unofficial API ToS risk is personal to this single-account tool; no multi-tenant exposure.

---

## Open Questions

1. **IGDB Switch category:** Confirm `category = 8` for Nintendo Switch in the IGDB `external_games` schema before implementation. If wrong, the IGDB matching pass will silently produce no Switch matches.
	1. where can we find the IGDB source of truth?
2. **Play activity endpoint:** The specific endpoint for per-game playtime data in the NSO API should be confirmed against current `nxapi` source before implementation — Nintendo has changed endpoint paths in past app updates. Verify field names (`totalPlayedMinutes`, `firstPlayedAt`, `lastPlayedAt`) match the current API response.
	1. Is that something you can find by searching git?
3. **Steam playtime column migration:** §5 proposes migrating Steam playtime into the new `play_time_mins` column for consistency. Confirm no downstream code in the preference agent or library view depends on the old Steam-specific column before dropping it.
	1. Sounds like a good idea
