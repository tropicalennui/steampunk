---
title: "US-006: Library JSON Export"
date: 2026-05-03
tags: [user-story, steam, pipeline, export]
status: draft
---

## As a...
A power user running SteamPunk locally

## I want to...
Have my enriched game library exported to `data/library.json` on demand

## So that...
I can inspect, back up, or pipe my library data into other tools without needing to query the database directly

## Acceptance Criteria

### Data pipeline
- [ ] After clicking the Export Data buttonS, `collect.py` writes the enriched library to `data/library.json`
- [ ] The JSON includes: game name, SteamID, playtime (minutes), genres, tags, and cover art URL
- [ ] `data/library.json` is gitignored
- [ ] If the `data/` directory does not exist it is created automatically

## Out of Scope (for now)
- Real-time export on library page load
- Export formats other than JSON
