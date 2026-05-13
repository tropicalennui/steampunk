---
title: "US-017: Automated Test Suite"
date: 2026-05-07
tags: [user-story, testing, quality]
status: done
---

## As a...
A developer maintaining and extending SteamPunk

## I want to...
Have an automated test suite that validates the pipeline, API routes, and schema against the acceptance criteria defined in each feature's user story

## So that...
Regressions are caught before merging, and new platform integrations can be verified structurally without requiring real credentials

## Acceptance Criteria

### Schema
- [x] Running `schema.sql` against an in-memory DuckDB produces all expected tables and columns
- [x] All platform rows are seeded correctly in the `platforms` table
- [x] `achievements` table has `gamerscore_earned` and `gamerscore_total` columns (US-016)
- [x] `library` table has `purchase_source` column

### Pipeline — stage/promote functions
- [x] `stage_xbox()` correctly upserts rows into `stg_xbox_library` with expected field mapping
- [x] `promote_xbox()` creates rows in `games`, `platform_games`, `library`, and `achievements` from staged data
- [x] `promote_xbox()` skips achievement rows where `achievements_total = 0`
- [x] `promote_xbox()` sets `library.purchase_source = 'unknown'` for all Xbox rows
- [x] All promote functions are idempotent — running twice produces the same result as running once
- [x] Equivalent stage/promote coverage for Steam, GOG, PSN, and Switch pipelines

### API routes
- [x] `GET /library` returns 200 for an authenticated session
- [x] `GET /setup` returns 200 and renders connected/disconnected state correctly per `gandalf.json` content
- [x] `POST /sync` with a valid platform name starts a background sync and redirects to `/logs`
- [x] `POST /sync` with an already-running sync redirects to `/logs` without starting a second sync
- [x] `GET /api/library/columns` returns expected column definitions

### IGDB matching
- [x] `igdb_lookup_by_external_id()` returns the correct game ID when the mock response contains a match
- [x] `igdb_lookup_by_external_id()` returns `None` when the mock response is empty

## Out of Scope
- Auth flows requiring real credentials (Xbox OAuth, PSN NPSSO, GOG, Switch)
- End-to-end browser / UI tests
- Performance or load testing
