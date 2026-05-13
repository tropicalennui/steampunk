---
title: "US-010: Nintendo Switch Integration"
date: 2026-05-03
tags: [user-story, nintendo, switch, library, multi-platform]
status: deferred
---

## As a...
A Nintendo Switch owner who tracks my gaming across multiple platforms

## I want to...
Connect my Nintendo Switch account so that my Switch game library is ingested into SteamPunk alongside my other platforms

## So that...
The preference agent has visibility into games I've played on Switch, and my recommendations are not skewed by the absence of an entire platform's worth of play history

## Acceptance Criteria

### Authentication
- [ ] Setup flow guides the user through obtaining the credentials required to access Nintendo's API (session token / NSO cookie, per the available community approach)
- [ ] Credentials are stored in `gandalf.json` only — never committed or surfaced in the UI
- [ ] If authentication expires or is revoked, the pipeline skips the Switch sync for that run and flags reconnection as required

### Library Sync
- [ ] Switch game library is fetched and stored in a `stg_switch_library` staging table
- [ ] Each game entry captures at minimum: title, play time (if available), last-played date (if available)
- [ ] Staged entries are promoted into `platform_games` under a `Nintendo Switch` platform row
- [ ] Sync is idempotent — re-running does not create duplicates

### Cross-Platform Matching
- [ ] Switch titles are matched to canonical `games` rows via IGDB (same strategy as GOG and PSN)
- [ ] Unmatched titles remain as Switch-only entries until a future sync resolves them
- [ ] Store availability pass evaluates Switch-owned games with a resolved IGDB match for Steam / GOG availability

### Preference Agent Integration
- [ ] Switch games appear in the agent's owned-games list with a Nintendo Switch platform tag
- [ ] Available play metrics (play time, last-played) are surfaced as engagement signals
- [ ] Switch games are eligible for quiz pair selection (US-009), particularly those with limited play data

### UI
- [ ] Library view shows Switch games with the Nintendo Switch platform badge
- [ ] Platform filter includes Nintendo Switch alongside Steam, GOG, and PlayStation

## Out of Scope (for now)
- Nintendo eShop price lookups
- Wish list or download list (not yet purchased) data
- Friend activity or social features
- Individual achievement / stamp detail beyond summary stats

## Open Questions
- Nintendo does not provide a public library API. What community approach (e.g. `nxapi`, NSO app API reverse engineering) is most stable and appropriate for personal use? To be resolved in the HLD.
- Play time availability: confirm what fields the Nintendo API actually exposes before committing to playtime as a signal.
- Is Nintendo Switch Online (NSO) membership required to access the API, or is a standard Nintendo Account sufficient?
