---
title: "US-021: PSN IGDB Matching"
date: 2026-05-09
tags: [user-story, igdb, psn, matching]
status: draft
---

## As a...
A gamer using SteamPunk who owns games on PlayStation Network

## I want to...
Have my PSN games matched to IGDB entries so they receive the same rich metadata (summary, developer, publisher, rating) as my Steam and Xbox games

## So that...
The game detail page shows IGDB metadata for PSN titles, and cross-platform store availability is checked correctly

---

## Background

PSN games in the database are keyed by `np_communication_id` (e.g. `NPWR20007_00`), which is a trophy/network communication identifier. IGDB's `external_games` table uses a different PSN identifier — likely the PlayStation Store concept ID or a numeric title ID. The two formats don't align, so external-ID lookup always returns empty and the name fallback also fails due to title-naming differences.

61 PSN games are currently unmatched.

## Acceptance Criteria

- [ ] Investigate what identifier format IGDB expects for `external_game_source = 36` (PSN) by inspecting a sample of IGDB's `external_games` records for known PSN titles
- [ ] Determine whether the PSN collector can be extended to capture a compatible ID (e.g. concept ID from the PSN API response) alongside `np_communication_id`
- [ ] If a compatible external ID is available: update the PSN collector to store it in `stg_psn_library`, update the `platform_games` matching to use it for IGDB lookups, and verify at least 50% of PSN titles match
- [ ] If no compatible external ID is available: document the finding and fall back to an improved name-based matching strategy (e.g. normalise punctuation, strip subtitles) with a target match rate
- [ ] PSN games that do match receive `igdb_id` on their `games` row and are picked up by the metadata pass

---

## Out of Scope
- Retroactive re-matching of games that were previously matched via name fallback
- IGDB trophy/achievement data for PSN
