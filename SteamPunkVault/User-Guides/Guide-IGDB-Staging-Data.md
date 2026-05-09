---
title: "Guide: IGDB Staging Data"
date: 2026-05-09
tags: [user-guide, igdb, metadata, detail-page]
story: "[[US-020: IGDB Staging Data]]"
---

## Overview

When a game is matched to an IGDB entry, SteamPunk fetches rich metadata — summary, developer, publisher, first release date, and aggregate rating — and stores it locally. This data appears as an **IGDB** section on the game detail page.

## Prerequisites

- IGDB game matching has run at least once (IGDB / Twitch sync) so games have an `igdb_id`
- IGDB credentials configured in `gandalf.json` under `igdb.client_id` and `igdb.client_secret`

## Step-by-Step

### 1. Run the IGDB sync

From the library page, click **Sync Now → IGDB / Twitch**, or run:

```bash
python src/collect.py --platforms igdb
```

The sync runs in two passes:
1. **Matching pass** — links unmatched games to IGDB entries
2. **Metadata pass** — fetches summary, developer, publisher, release date, and rating for newly matched games

The metadata pass only fetches games not yet in `stg_igdb`, so re-running is fast.

### 2. View metadata on the detail page

Open any game detail page (`/library/games/{id}`). If the game has an IGDB match, an **IGDB** section appears below Genres & Tags showing:

| Field | Notes |
|---|---|
| Summary | Truncated to ~300 chars; click **Read more** to expand |
| Developer | One or more companies |
| Publisher | One or more companies |
| First released | Date of first release across all platforms |
| Rating | Aggregate critic score out of 100, with rating count |

Fields are omitted individually if IGDB has no data for them. The entire section is absent if the game has no `igdb_id`.

## Troubleshooting

**IGDB section not showing**
: The game may not have been matched yet. Run an IGDB sync and check the sync log — if the game appears in "not found in IGDB" it has no match. Check [[Guide-IGDB-Game-Matching]] for matching details.

**Rating or developer missing**
: IGDB's coverage is incomplete for some titles. Fields are stored as NULL when the API returns no value — this is expected behaviour, not a bug.
