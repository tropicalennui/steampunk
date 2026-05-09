---
title: "HLD: IGDB Staging Data"
date: 2026-05-09
tags: [hld, igdb, metadata, staging, detail-page]
story: "[[US-020: IGDB Staging Data]]"
status: approved
---

## Overview

After IGDB game matching runs and `games.igdb_id` is populated, fetch rich metadata from IGDB (summary, developer, publisher, first release date, aggregate rating) and store it in a `stg_igdb` staging table keyed on `igdb_id`. Surface this data as an IGDB section on the game detail page.

## Goals & Non-Goals

**Goals**
- Collect IGDB metadata for every matched game and store it in `stg_igdb`.
- Key the staging table on `igdb_id` (not `game_id`) so rows survive game-row merges.
- Upsert on re-run so subsequent IGDB syncs can refresh metadata.
- Show an IGDB section on the game detail page when a `stg_igdb` row exists.

**Non-Goals**
- IGDB genres/themes (separate story).
- Screenshots or video embeds.
- Linking out to the IGDB website.
- Re-fetching metadata on every sync run — only fetch rows not yet in `stg_igdb`.

## Design

### 1. `stg_igdb` table (schema.sql)

```sql
CREATE TABLE IF NOT EXISTS stg_igdb (
    igdb_id                 INTEGER   PRIMARY KEY,
    summary                 VARCHAR,
    developer               VARCHAR[],
    publisher               VARCHAR[],
    first_release_date      DATE,
    aggregated_rating       DOUBLE,
    aggregated_rating_count INTEGER,
    collected_at            TIMESTAMP NOT NULL DEFAULT current_timestamp
);
```

Keyed on `igdb_id`, not `game_id`. If two `games` rows are later merged into one, both share the same `igdb_id` and therefore the same `stg_igdb` row — no cleanup needed.

### 2. IGDB API call

One `/games` query per `igdb_id`:

```
fields id, summary, aggregated_rating, aggregated_rating_count,
       first_release_date,
       involved_companies.company.name,
       involved_companies.developer,
       involved_companies.publisher;
where id = {igdb_id};
limit 1;
```

IGDB returns `first_release_date` as a Unix epoch (integer seconds). Convert to a Python `datetime.date` before storage.

`involved_companies` is a nested array. Flatten into two lists:
- `developer`: names where `involved_companies[*].developer == true`
- `publisher`: names where `involved_companies[*].publisher == true`

A company can appear in both lists; both are stored independently.

### 3. `run_igdb_metadata()` (igdb.py)

Called from `_sync_igdb()` after `run_igdb_matching()`. Strategy:

1. Query all `games.igdb_id` values that don't yet have a row in `stg_igdb`.
2. For each, call the IGDB `/games` endpoint with the query above.
3. Upsert into `stg_igdb` with `ON CONFLICT (igdb_id) DO UPDATE`.
4. Apply the existing 0.25 s rate-limit delay between calls.

On first run this collects all matched games. Subsequent IGDB syncs are near-instant (no missing rows, nothing to fetch).

### 4. Detail page — backend (`library.py`)

In `game_detail()`, after the existing platform queries, add:

```python
igdb_detail: dict = {}
if game["igdb_id"]:
    rows = _query(conn,
        "SELECT summary, developer, publisher, first_release_date, "
        "aggregated_rating, aggregated_rating_count "
        "FROM stg_igdb WHERE igdb_id = ?",
        [game["igdb_id"]])
    igdb_detail = rows[0] if rows else {}
```

Pass `igdb_detail` to the template context.

### 5. Detail page — template (`game_detail.html`)

Add an **IGDB** section below Genres & Tags, visible only when `igdb_detail` is non-empty:

- **Summary**: text block, truncated to ~300 chars at word boundary with a "Read more" toggle.
- **Developer / Publisher**: comma-joined from the arrays; omitted if empty.
- **First release date**: formatted `YYYY-MM-DD`; omitted if NULL.
- **Rating**: displayed as `{rating} / 100 ({count} ratings)`; omitted if NULL.

If `game.igdb_id` is NULL or `stg_igdb` has no row, the section is completely absent — no empty state.

## Data & Privacy Considerations

- `stg_igdb` stores publicly available game metadata fetched from the IGDB API. No PII.
- No secrets appear in staging data.

## Open Questions

None — design is fully specified.
