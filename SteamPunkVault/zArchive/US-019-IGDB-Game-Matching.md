---
title: "US-019: IGDB Game Matching"
date: 2026-05-09
tags: [user-story, igdb, matching, cross-platform, store-availability]
status: done
---

## As a...
A user with games spread across Steam, GOG, and PSN.

## I want to...
Have SteamPunk automatically match my library entries to IGDB records and check store availability across platforms, with IGDB runnable as a standalone sync step after my platform libraries are populated.

## So that...
I can see which games I own on one platform are also available on another, and my cross-platform library is deduplicated by a shared game identity rather than just title strings.

## Acceptance Criteria
- [x] IGDB credentials (`client_id`, `client_secret`) stored in `gandalf.json` under the `igdb` key.
- [x] IGDB matching runs after platform syncs, using the Twitch Client Credentials grant (no user login required).
- [x] External ID lookup uses the correct IGDB API field (`external_game_source`, not the deprecated `category`).
- [x] Name-based lookup fallback used when external ID yields no match.
- [x] When a matched IGDB ID already exists on a different `games` row, the duplicate is merged into the canonical row without data loss.
- [x] Store availability pass runs after matching, recording which platforms each matched game is available on.
- [x] IGDB is a selectable sync target in the UI dropdown so it can be run independently after platform libraries are populated.
- [x] "All platforms" removed from the sync dropdown — the Sync Now button covers that case.
