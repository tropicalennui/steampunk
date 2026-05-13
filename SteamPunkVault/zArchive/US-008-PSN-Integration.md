---
title: "US-008: PSN Integration"
date: 2026-05-03
tags: [user-story, psn, playstation, library, multi-platform]
depends-on: "[[US-003: GOG Integration & Normalised Multi-Platform Library]]"
status: done
---

## As a...
A user who owns games on PlayStation Network (PS4/PS5)

## I want to...
Connect my PSN account so my PlayStation library and trophy data are merged into the same normalised library as my Steam and GOG games

## So that...
I get a single unified view of my game catalogue across all platforms, and the preference agent can factor in my PlayStation play history and trophy engagement when making recommendations

## Acceptance Criteria

### Authentication
- [ ] Setup page has a "Connect PlayStation" option
- [ ] Authentication uses the NPSSO cookie flow (user pastes their NPSSO token from PlayStation.com)
- [ ] NPSSO token is exchanged for OAuth access + refresh tokens and stored in `gandalf.json`
- [ ] Expired / invalid tokens surface a "Reconnect PlayStation" prompt on the Setup page

### Library Sync
- [ ] Pipeline ingests the user's PSN game entitlements (owned games) and PS Plus catalogue games
- [ ] PS Plus games are tagged with a `subscription` source flag to distinguish them from purchased titles
- [ ] Each PSN game is staged in a `stg_psn_library` table
- [ ] Staged games are promoted into `platform_games` under a `PlayStation` platform entry
- [ ] Games with matching IGDB records are linked to the canonical `games` row (deduplicating titles also owned on Steam or GOG)

### Trophy Data
- [ ] Trophy summary (total trophies, completion %) is synced per game and stored alongside the PSN library entry
- [ ] Trophy completion rate is available as a preference-agent signal (same role as Steam achievement completion rate)

### UI
- [ ] PlayStation games appear in the unified library view alongside Steam and GOG titles
- [ ] Platform badge distinguishes PlayStation-sourced entries
- [ ] Cross-platform availability badges work for PlayStation-owned titles (e.g. "also on Steam")

### Pipeline
- [ ] PSN sync runs as a new step in `collect.py`, after GOG and before the IGDB matching pass
- [ ] All sync steps remain idempotent (upserts only)
- [ ] PSN credentials (`PSN_NPSSO`, access token, refresh token) are stored only in `gandalf.json`

## Notes
- **Unofficial API only** — Sony has no public API for personal game/trophy data. Auth uses the NPSSO cookie flow via `psnawp` (Python). Violates Sony ToS; account ban risk is low at personal-use request rates but credentials must be stored in `gandalf.json` and never committed.
- **Library completeness** — whether the API returns a full owned-games list or only trophy-tracked titles will be determined empirically during implementation.

## Out of Scope (for now)
- Friends / social / activity feed data
- PlayStation Store price lookups
- PS3 / Vita / PSP legacy library (PS4/PS5 titles only)
