---
title: "US-007: Pipeline Refresh Flag"
date: 2026-05-03
tags: [user-story, steam, pipeline, cli]
status: draft
---

## As a...
A user keeping my local library data up to date

## I want to...
Run `collect.py --refresh` to force a full re-fetch of all Steam data

## So that...
I can get the latest playtime, newly purchased games, and updated metadata without having to know the internal upsert behaviour

## Acceptance Criteria

### CLI
- [ ] `collect.py` accepts a `--refresh` flag
- [ ] When `--refresh` is passed, all existing data for the selected platforms is cleared before re-fetching
- [ ] Without `--refresh`, the pipeline upserts (existing behaviour is preserved)
- [ ] `--refresh` can be combined with `--platforms` to refresh a specific platform only

## Out of Scope (for now)
- Scheduled / automatic refresh
- Partial refresh by game ID
