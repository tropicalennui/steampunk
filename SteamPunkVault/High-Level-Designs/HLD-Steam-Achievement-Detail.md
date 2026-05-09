---
title: "HLD: Steam Achievement Detail"
date: 2026-05-09
tags: [hld, steam, achievements, detail-page]
story: "[[US-026: Steam Achievement Detail]]"
status: approved
---

## Overview

Extend the Steam achievements sync to store per-achievement data (icon, name, description, achieved status, unlock time) in a new staging table, then surface it as an icon grid on the game detail page.

## Goals & Non-Goals

**Goals**
- Store individual achievement data during the existing `steam:achievements` sync pass — no new sync step.
- Read directly from the staging table on the detail page (no canonical promotion needed — this is purely Steam-specific data).
- Show unlocked achievements before locked ones; icons clearly distinguish the two states.

**Non-Goals**
- Achievement descriptions always visible (hover only — avoids clutter for games with 100+ achievements).
- PSN trophy detail.

## Design

### 1. `stg_steam_achievement_details` table

```sql
CREATE TABLE IF NOT EXISTS stg_steam_achievement_details (
    app_id        INTEGER  NOT NULL,
    api_name      VARCHAR  NOT NULL,
    display_name  VARCHAR,
    description   VARCHAR,
    icon_url      VARCHAR,
    icon_gray_url VARCHAR,
    achieved      BOOLEAN  NOT NULL DEFAULT FALSE,
    unlock_time   TIMESTAMP,
    collected_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (app_id, api_name)
);
```

Keyed on `(app_id, api_name)` — survives game-row merges (same pattern as `stg_igdb`).

### 2. API calls

**`GetSchemaForGame/v2/`** — achievement definitions, icons, descriptions. Public endpoint, no privacy restriction, no `steamid` required.

```
GET https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/
    ?key=<api_key>&appid=<app_id>
```

Returns per-achievement: `name` (api_name), `displayName`, `description`, `icon` (unlocked URL), `icongray` (locked URL).

**`GetPlayerAchievements/v1/`** — already called by `fetch_achievements`. Returns per-achievement: `apiname`, `achieved` (0/1), `unlocktime` (epoch seconds, 0 if not unlocked).

### 3. Sync changes (`steam.py`)

Modify `fetch_achievements` to return the full achievement list alongside the summary:

```python
# Returns (unlocked, total, pct, achievements_list) or None
# achievements_list = [{"apiname": str, "achieved": bool, "unlocktime": int}]
```

Add `fetch_achievement_schema(app_id, api_key)`:

```python
# Returns {api_name: {"display_name", "description", "icon_url", "icon_gray_url"}}
# Returns {} on failure (not all games have a schema page)
```

In `_sync_steam_achievements`, for each game with achievement data:
1. Call `fetch_achievement_schema` (one extra API call per game, rate-limited to 0.25s)
2. Merge schema with player achievement list
3. Upsert into `stg_steam_achievement_details`

`fetch_achievements` summary tuple is unchanged — callers that only need counts continue to work.

### 4. Detail page — backend (`library.py`)

In `game_detail()`, after the existing platform queries, query `stg_steam_achievement_details` when the game has a Steam `platform_game`:

```python
achievement_details: list = []
if "steam" in platform_data:
    achievement_details = _query(conn,
        "SELECT display_name, description, icon_url, icon_gray_url, achieved, unlock_time "
        "FROM stg_steam_achievement_details WHERE app_id = ? "
        "ORDER BY achieved DESC, display_name",
        [int(platform_data["steam"]["external_id"])])
```

Pass `achievement_details` to the template context.

### 5. Detail page — template (`game_detail.html`)

Replace the plain summary `<dl>` entry for achievements with:

```
Summary line: "30 / 94  ·  32%"  (always shown when total_count > 0)

If achievement_details populated:
  Grid of icon tiles (6–8 per row, responsive)
  Each tile: 64×64 icon image, achievement name below, hover tooltip with description + unlock date
  Unlocked: full-colour icon, amber name text
  Locked: grey icon, zinc-600 name text
```

Icons are served directly from Steam CDN URLs — no proxying needed.

## Data & Privacy Considerations

- `GetSchemaForGame` is a public endpoint — no privacy concern.
- Icon URLs point to Steam's CDN (`steamcdn-a.akamaihd.net`) — loaded client-side, no PII.
- Achievement names and descriptions are public game data, not user PII.

## Open Questions

None — design fully specified.
