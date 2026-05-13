---
title: "US-013: Library View Modes & Card Merge"
date: 2026-05-04
tags: [user-story, library, grid-view, list-view, column-picker, card-merge, multi-platform]
status: draft
---

## As a...
A gamer with a multi-platform library

## I want to...
- Switch the library between a **grid view** (the current card layout) and a **list view** (a dense tabular layout)
- When in list view and filtered to a single platform, choose **which columns** of that platform's data are displayed or retained as hidden — drawn from both the platform's own staging table and the normalised `library` table; columns marked as important in the picker are candidates for promotion into the canonical `games` / `library` tables
- When a search returns more than one result in grid view, drag one card onto another to manually **merge** them into a single canonical game record

## So that...
- I can choose between a visual, cover-art-driven browse experience and a data-dense spreadsheet-style view depending on what I'm doing
- I can surface platform-specific fields (e.g. Steam playtime-2-weeks, PSN acquisition type, PS4/PS5 platform flag) that are stored in the DB but currently invisible in the UI
- I can correct missed IGDB auto-matches without leaving the app — consolidating split entries for the same game that the pipeline couldn't link automatically

---

## Acceptance Criteria

### Grid / List toggle
- [ ] A toggle control (e.g. grid icon / list icon) is present in the library header at all times
- [ ] The active view mode persists across page navigations within the session (e.g. via localStorage)
- [ ] Grid view is the default; List view is opt-in
- [ ] Both views respect the active platform filter, search query, and show-hidden state

### List view — base behaviour
- [ ] List view renders games as table rows; columns are sortable by clicking the column header
- [ ] Minimum always-visible columns: **Title**, **Platforms**, **Rating**
- [ ] All existing card-level actions (thumbs up/down, hide/unhide) are accessible from list rows
- [ ] Cover art is not shown in list view (space is at a premium); a small platform badge replaces it

### List view — column picker (platform-filtered)
- [ ] A **Columns** button appears in the list-view header only when a single-platform filter is active
- [ ] Clicking it opens a dropdown/panel listing every column available for that platform, grouped into two sections: **Platform data** (from the staging table) and **Library data** (from the normalised tables)
- [ ] Column availability by platform:

  | Column | Steam | GOG | PSN | Switch |
  |---|---|---|---|---|
  | Playtime (total) | ✓ | — | — | ✓ |
  | Playtime (last 2 weeks) | ✓ | — | — | — |
  | Last played | ✓ | — | — | — |
  | First played | ✓ | — | — | — |
  | Never launched | ✓ | — | — | — |
  | Release date | ✓ | ✓ | — | — |
  | Genres | ✓ | — | — | — |
  | Tags | ✓ | — | — | — |
  | Steam categories | ✓ | — | — | — |
  | Achievement % | ✓ | — | — | — |
  | Achievements unlocked / total | ✓ | — | — | — |
  | My review | ✓ | — | — | — |
  | Purchased at | ✓ | ✓ | ✓ | ✓ |
  | Purchase source | ✓ | ✓ | ✓ | ✓ |
  | PS platform (PS4/PS5) | — | — | ✓ | — |
  | Acquisition type | — | — | ✓ | — |
  | Trophy progress % | — | — | ✓ | — |
  | Trophies earned / defined | — | — | ✓ | — |

- [ ] Selected columns are persisted per-platform in localStorage (e.g. key `colPrefs_steam`)
- [ ] When "All" or "Multi-platform" filter is active, the Columns button is hidden and the list renders the base minimum columns only

### Card merge (search-scoped grid)
- [ ] Cards become draggable in grid view **only when a search query is active and has returned 2 or more results** — the intent is that the user searches for a game title, sees duplicate cards (from a missed IGDB auto-match), and drags one onto the other
- [ ] Dragging card A onto card B triggers a **merge confirmation modal** showing both game titles and their respective platforms, with a clear warning that this consolidates two `games` rows and cannot be undone without a full re-sync
- [ ] On confirmation the app calls `POST /library/games/merge` with `{ game_id_a, game_id_b }`:
  - The two `games` rows are collapsed into one; the surviving row retains the richer data (longer title wins, non-null cover wins)
  - All `platform_games` rows for both games are re-pointed to the surviving `games` row
  - `user_game_prefs`, `store_availability`, `game_tags`, `game_genres` rows are unioned into the surviving row (no data is discarded; if both had a rating, retain whichever is non-null, preferring `'up'` over `'down'` in a tie)
  - The redundant `games` row is deleted
- [ ] After a successful merge the grid refreshes; the merged card shows combined platform badges
- [ ] Dragging is disabled in list view and when fewer than 2 search results are visible
- [ ] A drag-in-progress state is visually indicated (dragged card lifts, drop target highlights with an amber border)

---

## Design Decisions

- **Column picker API approach:** AJAX / client-side. The column picker drives a `GET /library/games?platform=X&columns=a,b,c` fetch; the server returns only the requested fields as JSON. No full-page re-renders for column changes. This keeps server responses lean as the number of platforms and columns grows.

## Open Questions

1. **Normalisation candidates** — moved to [[US-014: Staging Data Analysis & Normalisation Candidates]]. The column picker will be designed to accept whatever fields US-014 defines as canonical; the list view endpoint will serve both staging-only and promoted fields transparently.

---

## Out of Scope
- Bulk column presets / saved views (one saved state per platform is sufficient)
- Undo / history for card merges (a full re-sync recovers the original state)
- Sorting persistence across sessions
- Column picker when "All" or "Multi-platform" filter is active
