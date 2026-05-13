---
title: "US-014: Staging Data Analysis & Normalisation Candidates"
date: 2026-05-04
tags: [user-story, data-analysis, normalisation, staging, canonical, library]
status: draft
---

## As a...
A developer maintaining the SteamPunk library pipeline

## I want to...
- Query each platform's staging table to understand what fields are actually populated, how consistently, and with what value distributions
- Based on that analysis, decide which staging fields are worth promoting into the canonical `games` or `library` tables (making them available cross-platform)
- Define the coalesce / merge logic for each promoted field (e.g. how to resolve conflicts when two platforms supply different values for the same field)

## So that...
- The list view column picker in [[US-013: Library View Modes & Card Merge]] can draw from a well-defined set of canonical fields rather than requiring raw staging table joins for every query
- Future platform integrations have a clear contract for which fields they must supply to contribute to the canonical layer

---

## Acceptance Criteria

### Data review
- [ ] For each staging table (`stg_steam_library`, `stg_steam_app_details`, `stg_steam_achievements`, `stg_steam_reviews`, `stg_gog_library`, `stg_psn_library`, `stg_switch_library`) run a population analysis:
  - Row count
  - Per-column: null %, distinct value count, sample values
- [ ] Produce a summary table of findings (saved as a reference note in `SteamPunkVault/`)

### Normalisation decisions
- [ ] For each field identified as a candidate for promotion, document:
  - Source table(s) and column name(s)
  - Which platforms supply it
  - Coalesce rule when multiple platforms have a value (e.g. prefer Steam playtime, use non-null, take max)
  - Target location in the canonical schema (new column on `games`, new column on `library`, new junction table, or new standalone table)
- [ ] Decisions reviewed and accepted before any schema migrations are written

### Schema changes
- [ ] For each accepted promotion, write the `ALTER TABLE` / `CREATE TABLE` migration in `src/schema.sql`
- [ ] Update `collect.py` promote step to populate the new canonical fields from staging data on each sync

---

## Out of Scope
- Changes to the list view UI (that is [[US-013: Library View Modes & Card Merge]])
- Normalising fields that are display-only and add no cross-platform value
