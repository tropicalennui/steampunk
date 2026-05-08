---
title: "HLD: Game Detail View & Unmerge"
date: 2026-05-05
tags: [hld, library, detail-view, unmerge, merge]
story: "[[US-015: Game Detail View & Unmerge]]"
status: implemented
---

## Overview

Add a full-page detail view for any game in the library, reachable by clicking its card. The page surfaces all platform-specific data held for that game in one place. For games built from a merge, it lists every absorbed entry with an individual Unmerge button so any or all can be separated back into independent cards.

## Goals & Non-Goals

**Goals**
- Full-page route `/library/games/{game_id}` — linkable, browser back-button navigable
- All per-platform data visible in a single view (playtime, trophies, achievements, review, tags, etc.)
- Per-entry Unmerge for games with one or more `merged_into` entries — handles 3+ copies
- Rating and hide actions available inline on the detail page
- After any unmerge the page reloads in place; after the last unmerge the Merged entries section disappears

**Non-Goals**
- Editing metadata (title, cover art) from the detail page
- Merging additional games from the detail page
- Deep-linking to a specific platform tab

---

## Design

### 1. Route & Template

```
GET /library/games/{game_id}
```

New FastAPI route rendering a new template `templates/game_detail.html`. Returns 404 if the game_id does not exist or has `merged_into IS NOT NULL` (merged-away entries are not addressable directly — the canonical game's page is the right place).

A breadcrumb at the top links back to `/library`.

### 2. Data Assembly

All data is fetched server-side and passed to the template. Seven targeted queries replace a single complex one for clarity:

```python
# 1. Canonical game row — 404 if not found or merged_into IS NOT NULL
game = _query(conn,
    "SELECT id, title, cover_url, igdb_id FROM games WHERE id = ? AND merged_into IS NULL",
    [game_id]
)

# 2. Platform ownership for canonical + all merged entries
#    Follows the same merged_into chain used by the library query
platform_rows = _query(conn, """
    SELECT p.slug, p.display_name, pg.external_id,
           l.playtime_mins, l.last_played_at, l.first_played_at,
           l.never_launched, l.purchased_at, l.purchase_source,
           COALESCE(a.completion_pct, 0.0) AS achievement_pct,
           a.unlocked_count, a.total_count,
           r.review_text
    FROM games g
    JOIN platform_games pg ON pg.game_id = g.id
    JOIN platforms p        ON p.id = pg.platform_id
    JOIN library l          ON l.platform_game_id = pg.id
    LEFT JOIN achievements a ON a.platform_game_id = pg.id
    LEFT JOIN reviews r      ON r.platform_game_id = pg.id
    WHERE g.id = ? OR g.merged_into = ?
    ORDER BY p.slug
""", [game_id, game_id])

# 3. Steam staging details (if steam in platform slugs)
steam_detail = _query(conn, """
    SELECT genres, tags, categories, release_date
    FROM stg_steam_app_details
    WHERE app_id = TRY_CAST(? AS INTEGER)
""", [steam_external_id])   # steam_external_id resolved from platform_rows

# 4. PSN staging details (if psn in platform slugs)
psn_detail = _query(conn, """
    SELECT platform, acquisition_type, trophy_progress,
           trophies_earned, trophies_defined
    FROM stg_psn_library WHERE np_communication_id = ?
""", [psn_external_id])

# 5. GOG staging details (if gog in platform slugs)
gog_detail = _query(conn,
    "SELECT release_date FROM stg_gog_library WHERE product_id = ?",
    [gog_external_id])

# 6. Genres, tags, store availability, user prefs
genres       = _query(conn, "SELECT gn.name FROM game_genres gg JOIN genres gn ON gn.id = gg.genre_id WHERE gg.game_id = ?", [game_id])
tags         = _query(conn, "SELECT t.name  FROM game_tags  gt JOIN tags   t  ON t.id  = gt.tag_id   WHERE gt.game_id = ?", [game_id])
availability = _query(conn, "SELECT platform_id, available FROM store_availability WHERE game_id = ?", [game_id])
prefs        = _query(conn, "SELECT rating, hidden FROM user_game_prefs WHERE game_id = ?", [game_id])

# 7. Merged entries — every game that was absorbed into this one
merged_entries = _query(conn, """
    SELECT g.id, g.title,
           list_distinct(list(p.slug)) AS platforms
    FROM games g
    JOIN platform_games pg ON pg.game_id = g.id
    JOIN platforms p        ON p.id = pg.platform_id
    WHERE g.merged_into = ?
    GROUP BY g.id, g.title
    ORDER BY g.title
""", [game_id])
```

### 3. Page Layout

```
┌─────────────────────────────────────────────────┐
│ ← Library                                        │
├──────────┬──────────────────────────────────────┤
│          │  Title                    [👍] [👎] [👁] │
│  Cover   │  Platform badges (clickable → section) │
│          │  Store availability badges             │
├──────────┴──────────────────────────────────────┤
│  [Steam]  [PSN]  [GOG]  [Switch]  ← section tabs │
│  ─────────────────────────────────────────────  │
│  Platform-specific stats for active tab          │
├─────────────────────────────────────────────────┤
│  Genres · Tags                                   │
├─────────────────────────────────────────────────┤
│  Merged entries  (only if merged_entries ≥ 1)    │
│  ┌──────────────────────────────────────────┐   │
│  │  "The Elder Scrolls V: Skyrim"  [PSN]     │   │
│  │                        [Unmerge]          │   │
│  ├──────────────────────────────────────────┤   │
│  │  "Skyrim"  [GOG]                          │   │
│  │                        [Unmerge]          │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

Platform tabs are rendered only for platforms the game is owned on. The active tab defaults to Steam if present, otherwise the first platform alphabetically.

Per-platform content:

| Platform | Fields shown |
|---|---|
| Steam | Playtime, last played, first played, never launched, achievement % (X/Y), genres, tags, Steam categories, my review |
| PSN | PS4 / PS5, acquisition type, trophy progress % (X/Y trophies) |
| GOG | Release date |
| Switch | Playtime |

### 4. Unmerge Endpoint

```
POST /library/games/{game_id}/unmerge
Body: { "entry_game_id": <int> }
Returns: { "unmerged_game_id": <int> }
```

Server logic:
1. Confirm `games WHERE id = entry_game_id AND merged_into = game_id` exists — return 400 if not
2. `UPDATE games SET merged_into = NULL WHERE id = entry_game_id`
3. Return `{ "unmerged_game_id": entry_game_id }`

No junction tables or `platform_games` are modified — the original data was never touched during merge so nothing needs restoring.

JS: on success, call `location.reload()`. The page re-renders with the updated merged entries list. If the list is now empty the section is not rendered.

### 5. Library Card Link

The existing `.game-card` template wraps the card body in an `<a href="/library/games/{{ game.game_id }}">` so clicking anywhere except the action buttons (thumbs, hide) navigates to the detail page. Action buttons use `event.preventDefault()` / `onclick` to avoid triggering the link.

---

## Data & Privacy Considerations

- No new data is stored or transmitted; the detail view reads existing tables only.
- Unmerge writes only `games.merged_into = NULL` — a reversal of a previously written value.
- The route returns 404 for merged-away entries so their `game_id` values are not browsable directly.

---

## Open Questions

1. **Tab persistence** — should the active platform tab persist across visits (localStorage) or always default to Steam? Defaulting to Steam is simpler; deferred until there is user feedback.
	1. default to steam. steam is required for this whole Steampunk thing to work.
2. **Switch playtime source** — detail page uses `library.playtime_mins` for Switch, consistent with the card. If US-014 promotes `stg_switch_library.play_time_mins` to a canonical column, update the query there.
	1. Switch is currently descoped and doesn't need to be considered.
