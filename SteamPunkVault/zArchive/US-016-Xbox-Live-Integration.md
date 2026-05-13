---
title: "US-016: Xbox Live Integration"
date: 2026-05-07
tags: [user-story, xbox, xbox-live, library, achievements, multi-platform]
status: done
---

## As a...
An Xbox player who tracks my gaming across multiple platforms

## I want to...
Connect my Xbox / Microsoft account so that my Xbox game library, playtime, and achievement data are ingested into SteamPunk alongside my other platforms

## So that...
The preference agent has full visibility into games I've played on Xbox (including Game Pass titles), and my recommendations are not skewed by the absence of an entire platform's worth of play history

## Acceptance Criteria

### Authentication
- [ ] Setup flow guides the user through a one-time OAuth2 browser login with their Microsoft account
- [ ] Resulting tokens are stored in `gandalf.json` only — never committed or surfaced in the UI
- [ ] Tokens are cached and auto-refreshed on subsequent syncs without requiring re-login
- [ ] If authentication expires or is revoked, the pipeline skips the Xbox sync for that run and flags reconnection as required

### Library Sync
- [ ] Xbox game library is fetched via `xbox-webapi-python` and stored in a `stg_xbox_library` staging table
- [ ] Each game entry captures at minimum: title, playtime (if available), last-played date (if available), and a `game_pass` boolean flag
- [ ] Game Pass titles (games played via subscription but not purchased) are included in the library and flagged with `game_pass = true`
- [ ] Staged entries are promoted into `platform_games` under an `Xbox` platform row
- [ ] Sync is idempotent — re-running does not create duplicates

### Achievements
- [ ] Per-game achievement detail is fetched and stored (achievement name, description, unlock status, unlock date) — consistent with Steam achievement storage
- [ ] Per-game Gamerscore summary (earned vs. total) is stored as a separate summary field alongside the raw achievements
- [ ] Achievement data is preserved for Game Pass titles even if subscription lapses

### Cross-Platform Matching
- [ ] Xbox titles are matched to canonical `games` rows via IGDB (same strategy as GOG, PSN, and Switch)
- [ ] Unmatched titles remain as Xbox-only entries until a future sync resolves them
- [ ] Store availability pass evaluates Xbox-owned (non-Game-Pass) games with a resolved IGDB match for Steam / GOG availability

### Preference Agent Integration
- [ ] Xbox games appear in the agent's game list with an Xbox platform tag
- [ ] Game Pass titles are surfaced to the agent with the `game_pass` flag so recommendations can distinguish subscription access from purchases
- [ ] Playtime and achievement completion % are surfaced as engagement signals
- [ ] Xbox games are eligible for quiz pair selection (US-009)

### UI
- [ ] Library view shows Xbox games with an Xbox platform badge
- [ ] Game Pass titles display a secondary "Game Pass" indicator distinct from the platform badge
- [ ] Platform filter includes Xbox alongside Steam, GOG, and PlayStation

## Out of Scope (for now)
- Xbox Store price lookups or wishlist data
- Friend activity or social/multiplayer features
- Gamerscore leaderboards or comparative stats
- Games for Windows Live (legacy) title support

## Open Questions
- Does `xbox-webapi-python` reliably expose the `acquisitionType` field to distinguish Game Pass from purchased titles? Research indicates the TitleHub wrapper likely does not surface this field — HLD specifies a best-effort fallback to `unknown`. Confirm empirically during implementation.
- What fields does the library endpoint actually return for playtime — confirm before committing to it as a signal.
- Is Microsoft account 2FA handled transparently by the OAuth flow, or does it require additional setup steps in the wizard?
