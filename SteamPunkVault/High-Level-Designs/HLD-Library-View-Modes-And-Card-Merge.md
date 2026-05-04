---
title: "HLD: Library View Modes & Card Merge"
date: 2026-05-04
tags: [hld, library, grid-view, list-view, column-picker, card-merge, ajax]
story: "[[US-013: Library View Modes & Card Merge]]"
status: draft
---

## Overview

Extend the library page with three related capabilities: a grid/list view toggle; a per-platform column picker in list view driven by an AJAX endpoint; and a search-scoped drag-to-merge gesture in grid view for manually consolidating game records that IGDB failed to auto-link.

## Goals & Non-Goals

**Goals**
- Grid/list toggle persisted in localStorage, visible at all times
- List view renders a sortable table; column set is configurable when a single-platform filter is active
- Column picker is data-driven from a server-side column registry — no hardcoded column lists in the frontend
- AJAX endpoint returns only the requested fields, keeping payloads lean
- Drag-to-merge available in grid view when a search returns 2+ results
- Merge collapses two canonical `games` rows into one; all related rows re-pointed; no data discarded

**Non-Goals**
- Pagination or virtual scrolling in list view (out of scope until library size warrants it)
- Saved/named column presets beyond one persisted selection per platform
- Undo for card merges (a full re-sync restores the original staging data)
- Normalisation of staging fields into new canonical columns (tracked separately in [[US-014: Staging Data Analysis & Normalisation Candidates]])
- Column picker when "All" or "Multi-platform" filter is active

---

## Design

### 1. Grid / List Toggle

A two-icon toggle (grid / list) is added to the library header alongside the existing sync button and search box. State is stored in `localStorage` under key `libraryViewMode` (`'grid'` or `'list'`); `'grid'` is the default.

On toggle:
- Grid view: the existing `#game-grid` element is shown; the list container is hidden
- List view: the grid is hidden; the list container (see §2) is shown and, if not yet populated, triggers an initial AJAX fetch

Both views share the same platform filter pills, search input, and show-hidden toggle — all three feed into whichever view is currently active.

No server-side change is required for the toggle itself.

---

### 2. List View — Base Behaviour

The list view renders an HTML `<table>` inside a `#game-list` container. Rows are fetched via AJAX (see §3).

**Always-visible columns:** Title, Platforms, Rating. These are present regardless of platform filter or column picker selection and cannot be deselected.

**Sorting:** Clicking a column header sorts ascending; clicking again sorts descending. Sort state is held in JS memory only (not persisted). Sorting is applied client-side to the current result set — no re-fetch required.

**Row actions:** Each row has a trailing actions cell containing the thumbs-up, thumbs-down, and hide/unhide buttons. These call the existing `PUT /library/games/{id}/rating` and `PUT /library/games/{id}/hidden` endpoints — no change to those APIs.

**Cover art** is omitted from list view. Platform badges (Steam / GOG / PSN / Switch coloured pills) replace it in the Platforms column.

**Search and platform filter** drive a re-fetch (debounced 300 ms for search) rather than client-side DOM filtering. The list view does not carry all game data in the DOM.

---

### 3. List View API — Column Resolution

#### 3.1 Endpoints

```
GET /api/library/columns?platform=<slug>
```
Returns the available column definitions for the given platform. Used to populate the column picker. Response:

```json
{
  "platform": "steam",
  "groups": [
    {
      "label": "Library data",
      "columns": [
        { "key": "playtime_mins",      "label": "Playtime (total)",        "default": true  },
        { "key": "last_played_at",     "label": "Last played",             "default": true  },
        { "key": "first_played_at",    "label": "First played",            "default": false },
        { "key": "never_launched",     "label": "Never launched",          "default": false },
        { "key": "purchased_at",       "label": "Purchased at",            "default": false },
        { "key": "purchase_source",    "label": "Purchase source",         "default": false }
      ]
    },
    {
      "label": "Platform data",
      "columns": [
        { "key": "playtime_2weeks",    "label": "Playtime (last 2 weeks)", "default": false },
        { "key": "release_date",       "label": "Release date",            "default": false },
        { "key": "genres",             "label": "Genres",                  "default": true  },
        { "key": "tags",               "label": "Tags",                    "default": false },
        { "key": "steam_categories",   "label": "Steam categories",        "default": false },
        { "key": "achievement_pct",    "label": "Achievement %",           "default": true  },
        { "key": "achievements_count", "label": "Achievements (earned/total)", "default": false },
        { "key": "my_review",          "label": "My review",               "default": false }
      ]
    }
  ]
}
```

Platform availability (which slugs expose which column keys):

| Key | steam | gog | psn | switch |
|---|---|---|---|---|
| `playtime_mins` | ✓ | — | — | ✓ |
| `last_played_at` | ✓ | — | — | — |
| `first_played_at` | ✓ | — | — | — |
| `never_launched` | ✓ | — | — | — |
| `purchased_at` | ✓ | ✓ | ✓ | ✓ |
| `purchase_source` | ✓ | ✓ | ✓ | ✓ |
| `playtime_2weeks` | ✓ | — | — | — |
| `release_date` | ✓ | ✓ | — | — |
| `genres` | ✓ | — | — | — |
| `tags` | ✓ | — | — | — |
| `steam_categories` | ✓ | — | — | — |
| `achievement_pct` | ✓ | — | — | — |
| `achievements_count` | ✓ | — | — | — |
| `my_review` | ✓ | — | — | — |
| `psn_platform` | — | — | ✓ | — |
| `acquisition_type` | — | — | ✓ | — |
| `trophy_pct` | — | — | ✓ | — |
| `trophies_count` | — | — | ✓ | — |

```
GET /api/library/games?platform=<slug>&columns=<key,key,...>&q=<search>&show_hidden=<bool>
```
Returns the game rows for the list view. `platform` and `columns` are optional; omitting `platform` returns all games with base columns only. `q` and `show_hidden` mirror the existing filter behaviour.

Response (example):
```json
{
  "games": [
    {
      "game_id": 42,
      "title": "The Witcher 3",
      "platforms": ["steam", "gog"],
      "rating": "up",
      "hidden": false,
      "playtime_mins": 4320,
      "achievement_pct": 61.5,
      "genres": ["RPG", "Open World"]
    }
  ]
}
```

#### 3.2 Server-side Column Registry

The server maintains a `COLUMN_REGISTRY` dict mapping each column key to its SQL resolution:

```python
COLUMN_REGISTRY = {
    "playtime_mins": ColumnDef(
        select="l.playtime_mins",
        join=None,   # library already joined in base query
        platforms={"steam", "switch"},
    ),
    "playtime_2weeks": ColumnDef(
        select="ssl.playtime_2weeks_mins",
        join="LEFT JOIN stg_steam_library ssl ON ssl.app_id = CAST(pg.external_id AS INTEGER)",
        platforms={"steam"},
    ),
    "genres": ColumnDef(
        select="array_agg(DISTINCT gn.name) FILTER (WHERE gn.name IS NOT NULL) AS genres",
        join="LEFT JOIN game_genres gg ON gg.game_id = g.id LEFT JOIN genres gn ON gn.id = gg.genre_id",
        platforms={"steam"},
    ),
    # ... etc
}
```

The endpoint validates that each requested key exists in the registry and is available for the requested platform, then assembles the query by appending the relevant `SELECT` fragments and `JOIN` clauses. Unknown or unavailable keys are silently dropped (no 400 error — the client may have a stale localStorage selection).

#### 3.3 Base Query

All list view queries share this base (platform filter applied when `platform` param is present):

```sql
SELECT
    g.id           AS game_id,
    g.title,
    array_agg(DISTINCT p.slug) AS platforms,
    ugp.rating,
    ugp.hidden
    -- requested column SELECTs appended here
FROM games g
JOIN platform_games pg ON pg.game_id = g.id
JOIN platforms p ON p.id = pg.platform_id
JOIN library l ON l.platform_game_id = pg.id
LEFT JOIN user_game_prefs ugp ON ugp.game_id = g.id
-- requested column JOINs appended here
WHERE p.slug = :platform           -- omitted if platform is null
  AND (:q IS NULL OR lower(g.title) LIKE '%' || lower(:q) || '%')
  AND (:show_hidden OR ugp.hidden IS NOT TRUE)
GROUP BY g.id, g.title, ugp.rating, ugp.hidden
         -- non-aggregate requested columns appended here
ORDER BY lower(g.title)
```

---

### 4. Column Picker UI

The **Columns** button appears in the list view toolbar only when a single-platform filter pill is active. It is hidden when "All" or "Multi-platform" is selected.

On click, a dropdown panel renders the column groups returned by `GET /api/library/columns?platform=<slug>`. Each column is a checkbox; checked = visible. The always-visible base columns (Title, Platforms, Rating) are shown as pre-checked and disabled.

**Persistence:** On any checkbox change, the current selection is written to `localStorage` under `colPrefs_<platform>` (e.g. `colPrefs_steam`) as a JSON array of active keys. On page load, the stored selection is applied before the first fetch.

**First load for a platform with no stored prefs:** columns where `default: true` in the registry response are pre-selected.

**Fetch trigger:** Any change to column selection triggers a debounced (150 ms) re-fetch of `GET /api/library/games` with the new column list.

---

### 5. Card Drag-to-Merge

#### 5.1 Enabling Condition

Drag handles are activated dynamically in grid view whenever:
1. The search input is non-empty, **and**
2. The current visible card count is ≥ 2

When the condition is met, all visible `.game-card` elements receive `draggable="true"` and a subtle drag-handle indicator. When the condition is no longer met (search cleared, or only one result), `draggable` is removed.

Drag-to-merge is disabled entirely in list view.

#### 5.2 Drag Interaction

- **Drag start:** the dragged card gets a lifted visual state (slight scale + shadow).
- **Drag over a valid target:** the target card gains an amber border highlight (`border-amber-500`). A card cannot be its own drop target.
- **Drop:** the merge confirmation modal opens (see §5.3). The drag visual states are cleared regardless of modal outcome.

HTML5 Drag and Drop API is used directly — no JS library required for this interaction.

#### 5.3 Merge Confirmation Modal

The modal shows:
- Both game titles and their platform badges side-by-side
- A plain-English summary: *"These two entries will be collapsed into one game. All platform data will be combined. This cannot be undone without a full re-sync."*
- **Confirm merge** (amber) and **Cancel** (zinc) buttons

#### 5.4 Merge Endpoint

```
POST /library/games/merge
Body: { "game_id_a": <int>, "game_id_b": <int> }
```

The endpoint is symmetric — there is no source/target. Both `games` rows collapse into one canonical record. Server-side logic:

1. **Determine surviving row:** prefer the row with the greater number of associated `platform_games` rows; if equal, prefer the lower `id`.
2. **Surviving `games` fields:**
   - `title`: longer of the two non-empty strings
   - `cover_url`: first non-null (prefer surviving row's value)
   - `igdb_id`: first non-null
3. **Re-point `platform_games`:** all rows where `game_id` = redundant ID → set to surviving ID.
4. **`game_tags` / `game_genres`:** `INSERT OR IGNORE` all rows from redundant ID into surviving ID (union, no duplicates).
5. **`user_game_prefs`:** if only one row exists across both IDs, re-point it; if both exist, keep surviving row's values and discard redundant row's (preference data for the more-played copy is more reliable).
6. **`store_availability`:** `INSERT OR IGNORE` all rows from redundant ID into surviving ID.
7. **Delete** redundant `games` row (cascade or explicit delete of child rows first if FK constraints require it).
8. Return `{ "surviving_game_id": <int> }` on success.

On success the client removes both cards from the DOM and re-fetches the surviving game card to insert in their place.

---

## Data & Privacy Considerations

- No new PII is introduced. Merge operates entirely on existing DB rows.
- `POST /library/games/merge` is a destructive operation on the local database. It is not reversible via the UI; the user is warned in the confirmation modal. A full re-sync (which re-runs the IGDB matching pass) would recreate split records if the IGDB match still fails.
- No data is sent to any external service as part of this feature.

---

## Open Questions

1. **Normalisation candidates** — column keys that represent staging-only fields (e.g. `playtime_2weeks`, `psn_platform`) are served directly from staging tables. Once [[US-014: Staging Data Analysis & Normalisation Candidates]] is complete, some of these may be promoted to canonical columns; the registry `ColumnDef.join` for those keys would be updated to point at the canonical table instead. No API contract change required.
