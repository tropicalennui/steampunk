---
title: "HLD: IGDB Game Matching"
date: 2026-05-09
tags: [hld, igdb, matching, cross-platform, store-availability]
story: "[[US-019: IGDB Game Matching]]"
status: implemented
---

## Overview

Use IGDB (Twitch's game database) to resolve a shared identity for games owned across multiple platforms, then check store availability for each matched game. IGDB runs as a post-platform-sync pass and can also be triggered independently from the UI.

## Goals & Non-Goals

**Goals**
- Match each `platform_games` row to an IGDB game ID using the platform's external ID, with a name-based fallback.
- Merge `games` rows that resolve to the same IGDB ID (cross-platform duplicates).
- Record store availability (is this Steam game also on GOG? etc.) for matched games.
- Allow IGDB sync to run independently after platform libraries are fully populated.

**Non-Goals**
- Fuzzy / probabilistic title matching — exact name match is the fallback ceiling.
- IGDB metadata enrichment (cover art, genres from IGDB) — covered by platform-native data.
- Automated conflict resolution for non-obvious merges — ambiguous cases are logged and skipped.

## Design

### 1. Credentials & Authentication

IGDB is operated by Twitch. Access requires a Twitch developer application registered at `dev.twitch.tv/console`:

- **OAuth Redirect URL:** `https://localhost` (placeholder — the Client Credentials grant never redirects)
- **Category:** Analytics Tool
- **Client Type:** Confidential (secret is bundled in the controlled binary, never exposed to end users)

Credentials stored in `gandalf.json`:
```json
{
  "igdb": {
    "client_id": "...",
    "client_secret": "..."
  }
}
```

A short-lived access token is obtained per-sync via the Twitch Client Credentials flow (`POST https://id.twitch.tv/oauth2/token`). No user login or browser redirect occurs.

### 2. Matching Strategy

For each `platform_games` row whose parent `games` row has no `igdb_id`:

**Step 1 — External ID lookup:**
Query `POST /external_games` with `external_game_source = {source} & uid = "{external_id}"`.

| Platform | `external_game_source` | `uid` format |
|---|---|---|
| Steam | 1 | Steam App ID (e.g. `"72850"`) |
| GOG | 5 | GOG product ID |
| PSN | 36 | PlayStation Store concept ID |

> **Note:** The IGDB API previously used a field called `category` for this filter. It was renamed to `external_game_source`. The `category` field silently returns empty results — always use `external_game_source`.

IGDB's `external_games` dataset has incomplete coverage (many major titles have no external ID entry). The external ID lookup is attempted first but will often return empty.

**Step 2 — Name fallback:**
If step 1 returns no match, query `POST /games` with `name = "{title}" & version_parent = null`. This matches the base game only (excludes DLC and version parents).

**Step 3 — Merge or tag:**
- If the returned IGDB game ID already exists on a different `games` row: merge the duplicate into the canonical row (see §3).
- Otherwise: set `igdb_id` on the current `games` row.

Switch and Xbox platform games are skipped in the matching pass — IGDB's `external_games` coverage for those platforms is insufficient to be reliable.

### 3. Merge Logic & DuckDB FK Workaround

When two `games` rows resolve to the same `igdb_id`, the duplicate is merged into the canonical row via `_merge_games_rows`:

1. Re-point `platform_games.game_id` from duplicate → canonical.
2. Copy `game_genres`, `game_tags`, `store_availability`, and `user_game_prefs` to canonical; delete duplicates.
3. Delete the duplicate `games` row.

**DuckDB FK limitation:** DuckDB treats `UPDATE` as `DELETE + INSERT` internally for foreign key constraint checking. Updating `platform_games.game_id` therefore triggers FK violation checks from `library`, `wishlist`, `achievements`, and `reviews` (all reference `platform_games.id`). Workaround: save and delete referencing rows before the update, perform the update, then re-insert the saved rows.

### 4. Store Availability Pass

After matching, for each game with an `igdb_id`, check whether it exists on platforms the user does not own it on:

- Steam-only games → check GOG availability (`external_game_source = 5`)
- GOG-only games → check Steam availability (`external_game_source = 1`)
- PSN-only games → check Steam and GOG availability

Results written to `store_availability (game_id, platform_id, available, external_id, checked_at)`. Rows older than 7 days are re-checked on the next IGDB sync.

### 5. Sync Pipeline Integration

IGDB runs as a named step in the sync pipeline, controlled by the `platforms` set:

```
run(platforms={"steam", "gog", "psn", "switch", "xbox", "igdb"})
```

- When `"igdb"` is in `platforms`: matching and availability passes run.
- When absent: both passes are skipped with a log message.
- The UI sync dropdown exposes "IGDB / Twitch" as a standalone option, allowing the user to run just the IGDB pass after all platform libraries have been populated.

### 6. API Rate Limiting

A 0.25s delay is applied between each IGDB API call. At 316 platform games × 2 calls (external ID + name fallback), worst-case runtime is ~2.5 minutes.

## Data & Privacy Considerations

- `igdb.client_id` and `igdb.client_secret` stored only in `gandalf.json` (gitignored).
- No IGDB data is committed to the repository.
- The Twitch access token is ephemeral (per-sync, not persisted).

## Open Questions

1. Nintendo Switch and Xbox matching — IGDB `external_games` coverage is sparse for these platforms. May be addressable with name-based matching only, if confidence thresholds are introduced.
2. PSN `external_id` format — PSN concept IDs in our database may not align with IGDB's PSN `uid` format. Needs validation once PSN library data is larger.
