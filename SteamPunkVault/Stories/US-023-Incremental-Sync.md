---
title: "US-023: Incremental Sync"
date: 2026-05-09
tags: [user-story, sync, performance, pipeline]
status: draft
---

## As a...
A gamer using SteamPunk who syncs their library regularly

## I want to...
Have full syncs complete faster by skipping enrichment data that has already been collected and is unlikely to have changed

## So that...
Syncing feels snappy day-to-day, and API rate limits are not wasted re-fetching static data on every run

---

## Background

The sync pipeline has two distinct categories of data:

| Category | Examples | Changes? | Delta strategy |
|---|---|---|---|
| Live user data | Playtime, achievements, trophies, library membership | Every session | Always fetch — this is the point of syncing |
| Static enrichment | Steam app details (genres, tags, cover, categories), GOG release date / cover | Rarely | Skip if already collected; re-fetch on staleness window |
| Cross-platform enrichment | IGDB metadata (`stg_igdb`), store availability | Rarely / weekly | Already delta — no change needed |

The IGDB passes already implement delta logic. This story applies the same pattern to platform enrichment data.

## Acceptance Criteria

### Steam
- [ ] `stg_steam_app_details` rows with a `collected_at` within the staleness window are skipped during app-detail fetching
- [ ] App IDs with no existing `stg_steam_app_details` row are always fetched (new games)
- [ ] A `--full` flag (or equivalent) on `collect.py` bypasses the staleness check and re-fetches all app details

### GOG
- [ ] `stg_gog_library` rows that already have `release_date` and `cover_url` populated and are within the staleness window are not re-fetched
- [ ] New GOG games (no existing row) are always fetched in full

### Staleness window
- [ ] Default staleness window is **30 days** (configurable via a constant, not hardcoded in multiple places)
- [ ] `collected_at` on each staging table drives the staleness check

### Observability
- [ ] Sync log reports how many records were skipped vs fetched for each enrichment step, e.g. `"48 app details fetched, 271 skipped (fresh)"`

---

## Out of Scope
- Delta detection for live user data (playtime, achievements) — always fetch
- Delta for library membership lists (new game detection requires a full list fetch)
- Smart invalidation based on Steam/GOG changelog events
