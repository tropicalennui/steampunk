---
title: "US-003: GOG Integration & Normalised Multi-Platform Library"
date: 2026-05-02
tags: [user-story, gog, steam, library, multi-platform, hide]
depends-on: "[[US-001: Steam Auth & Library Viewer]]"
status: done
---

## As a...
A user with games on both Steam and GOG

## I want to...
See my complete game library from both platforms in a single normalised view — knowing when I own a game on multiple platforms, where I can buy games I don't own yet on each store, and with the ability to hide individual games

## So that...
I have one place to manage my entire library across platforms, surface gaps in my collection, and filter out noise from games I no longer care about

## Acceptance Criteria

### GOG Authentication
- [x] App presents a "Connect GOG" option on the Setup page (alongside the existing Steam session cookie setup)
- [x] GOG authentication uses the OAuth2 flow at `auth.gog.com` (community credentials stored in `gandalf.json`)
- [x] On successful connection, GOG access and refresh tokens are stored in `gandalf.json` (never committed)
- [x] Token refresh is handled automatically when the access token expires
- [x] User can disconnect GOG from the Setup page, which removes the tokens from `gandalf.json`

### GOG Library Sync
- [x] `collect.py` fetches the authenticated user's full GOG games library via the unofficial GOG web API
- [x] Per-game data collected: GOG product ID, title, release date, and cover image URL
- [x] Raw data is staged in `stg_gog_library` before promotion to canonical tables
- [x] GOG is registered as a platform in the `platforms` table
- [x] Sync respects rate limits and logs progress to `logs/`

### Cross-Platform Game Matching
- [x] During the promote step, each game is looked up against the IGDB API by external platform ID (Steam app_id / GOG product_id)
- [x] If an IGDB match is found, the game's `igdb_id` is stored on the canonical `games` row
- [x] Games that share an `igdb_id` across platforms are linked to the same `games` row
- [x] Unmatched games remain as separate `games` rows (no forced deduplication)

### Cross-Platform Ownership Display
- [x] The Games List page shows a platform badge for every platform the user owns that game on
- [ ] A "multi-platform" indicator is shown for any game owned on more than one platform
- [ ] Games List can be filtered by platform (Steam / GOG / multi-platform)

### Store Availability
- [x] For every game the user owns on GOG but not on Steam, the app checks whether the game is available for purchase on the Steam store
- [x] For every game the user owns on Steam but not on GOG, the app checks whether the game is available for purchase on the GOG store
- [x] Store availability is resolved via IGDB `external_games` data (not by scraping store pages)
- [x] Store availability results are cached in the database with a `checked_at` timestamp; they are not re-checked on every sync
- [x] The Games List shows a "Available on Steam" or "Available on GOG" badge for applicable games

### Hide Games
- [x] User can hide any game from the library view via a hide action on the game card
- [x] Hidden games are excluded from the default Games List view
- [x] A "Show hidden" toggle at the top of the Games List reveals hidden games (visually distinct)
- [x] User can unhide a game from the "Show hidden" view
- [x] Hidden state is stored per user per game in the database

### Data Pipeline
- [x] All new fields (GOG platform, cross-platform links, store availability, hidden) are populated by `collect.py`
- [x] Sync is additive — re-running does not duplicate or erase user-set hidden flags

## Out of Scope (for now)
- GOG achievement data
- GOG wishlist
- Other platforms (Epic, Xbox, PlayStation)
- Price data for available-on-store games
- Bulk hide operations
- Game ratings (moved to [[US-004: Game Ratings]])
