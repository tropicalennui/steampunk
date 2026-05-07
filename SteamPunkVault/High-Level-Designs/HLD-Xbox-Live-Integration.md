---
title: "HLD: Xbox Live Integration"
date: 2026-05-07
tags: [hld, xbox, xbox-live, library, achievements, gamerscore, multi-platform]
story: "[[US-016: Xbox Live Integration]]"
status: implemented
---

## Overview

Extend the multi-platform library pipeline to ingest the user's Xbox game library and achievement data via the community `xbox-webapi-python` library. Xbox entries are deduplicated against existing titles via IGDB and merged into the canonical `games` table. Achievement completion rate and Gamerscore feed the preference agent as engagement signals. Playtime is not available via the TitleHub API. Game Pass acquisition cannot be detected from the TitleHub response — all Xbox entries carry `purchase_source = 'unknown'`, documented as a known limitation.

## Goals & Non-Goals

**Goals**
- Authenticate with Xbox Live via OAuth2 (Microsoft account) and persist tokens in `gandalf.json`
- Sync the user's Xbox game library (purchased + Game Pass) into `stg_xbox_library`
- Promote staged games into `platform_games` under an `Xbox` platform row
- Sync per-game achievement summary and Gamerscore as engagement signals
- Link Xbox titles to canonical `games` rows via IGDB matching
- Surface cross-platform store availability badges for all Xbox library titles

**Non-Goals**
- Friends / social / presence data
- Xbox Store price lookups or wishlist
- Gamertag leaderboards or comparative Gamerscore stats
- Games for Windows Live (legacy) title support
- Xbox 360 backwards-compat titles (include if they appear naturally in the API; no special handling)

---

## Design

### 1. Xbox Authentication

Microsoft does not offer a public consumer API for personal library data. The community `xbox-webapi-python` library (PyPI: `xbox-webapi`) implements OAuth2 against Microsoft's identity platform using a standard browser-based consent flow.

**Client credentials:** The library ships with OpenXbox community OAuth client credentials (`client_id` / `client_secret`) that work for personal-use projects — no Azure AD app registration required. These are stored in `gandalf.json` under `xbox.client_id` and `xbox.client_secret` (consistent with how GOG Galaxy credentials are handled).

**Flow:**
1. `collect.py` detects that `gandalf.json` has no `xbox.access_token` (or that `xbox.auth_expired = true`)
2. User is directed to a Microsoft login URL opened in their default browser using the OpenXbox client credentials
3. After consent, the OAuth2 callback delivers an authorization code that `xbox-webapi-python` exchanges for `access_token` + `refresh_token`
4. Tokens stored in `gandalf.json` under `xbox.access_token`, `xbox.refresh_token`, `xbox.expires_at`

**Token refresh:** `collect.py` checks `xbox.expires_at` before each Xbox API call and refreshes proactively if within 60 seconds of expiry using `xbox-webapi-python`'s built-in refresh flow.

**Expired / revoked token:** If the refresh fails, `collect.py` logs the error, skips Xbox sync for that run, and sets `xbox.auth_expired = true` in `gandalf.json`. The Setup page reads this flag and displays a "Reconnect Xbox" prompt. The flag is cleared on successful re-authentication.

**2FA:** Microsoft account 2FA is handled within the browser login flow and does not require special handling in the pipeline.

**Credentials:** `xbox.client_id`, `xbox.client_secret`, `xbox.access_token`, `xbox.refresh_token` stored only in `gandalf.json` (gitignored). Never committed, never in the database.

**ToS note:** `xbox-webapi-python` wraps unofficial/reverse-engineered endpoints not sanctioned by Microsoft. Risk at personal single-account usage rates is low.

---

### 2. Library & Achievement Sync

#### 2a. Library

`xbox-webapi-python` exposes a TitleHub provider that returns the user's game history — all titles where any activity (achievement unlock, launch) has been recorded.

**API call:**
```python
response = await client.titlehub.get_title_history(
    xuid=xuid,
    fields=[TitleFields.ACHIEVEMENT, TitleFields.TITLE_HISTORY],
    max_items=2000,
)
```

`max_items=2000` is used as a ceiling — the API has no pagination mechanism, so a single call with a high cap retrieves the full library. For a personal account this is sufficient.

**Fields returned per title:** `title_id`, `name`, last-played timestamp (from `title_history`), achievement summary (earned count, total count, Gamerscore earned, Gamerscore total from `achievement`). **Playtime is not available** via TitleHub — confirmed absent from the response model.

**Game Pass detection:** The TitleHub `game_pass.is_game_pass` field indicates whether a title is *currently available* on Game Pass, not how the user acquired it. Acquisition history is not exposed by the API at the access level available to personal apps. All Xbox rows are written with `library.purchase_source = 'unknown'`. This is a known limitation documented in the User Guide.

**Staging table (new):**
```sql
stg_xbox_library (
  title_id            VARCHAR PRIMARY KEY,   -- Xbox titleId
  title               VARCHAR,
  last_played         TIMESTAMP,
  achievements_earned INTEGER,
  achievements_total  INTEGER,
  gamerscore_earned   INTEGER,
  gamerscore_total    INTEGER,
  collected_at        TIMESTAMP
)
```

**Promote step:** Upsert from `stg_xbox_library` into `platform_games` using `title_id` as `external_id`. The `Xbox` row in `platforms` is the `platform_id`. Write `library.purchase_source = 'unknown'` for all Xbox rows. Write achievement and Gamerscore summary to the `achievements` table (see §2b).

#### 2b. Achievement & Gamerscore Summary

The TitleHub response includes a per-title achievement summary — earned count, total count, Gamerscore earned, and Gamerscore total. No separate per-achievement API call is needed; all data comes from the library pass already.

**Mapping to `achievements` table** (summary row, one per `platform_game_id` — same structure as PSN and Steam):

| `achievements` column | Source |
|---|---|
| `platform_game_id` | `platform_games.id` for this Xbox title |
| `unlocked_count` | achievements earned |
| `total_count` | total achievements defined |
| `completion_pct` | `unlocked_count / total_count * 100` |
| `gamerscore_earned` | Gamerscore earned (new column — see §5) |
| `gamerscore_total` | Gamerscore total (new column — see §5) |

Achievement data is preserved in the database regardless of whether Game Pass access lapses — it reflects historical activity, not current entitlement. Achievement sync is skipped for titles where `total_count = 0`.

---

### 3. Cross-Platform Game Matching via IGDB

Xbox titles are matched to canonical `games` rows using the same IGDB `external_games` strategy as GOG, PSN, and Switch.

**IGDB category for Xbox:** Confirm the correct `category` value for Xbox One / Xbox Series in the IGDB `external_games` schema during implementation (likely `category = 11` for Xbox 360, `category = 49` for Xbox One — verify against live API before coding).

**Matching strategy:** Identical to the established pattern — score candidates on title similarity + publisher + release year, accept only above the confidence threshold, log near-misses, flag conflicts for manual review rather than auto-merging.

**Fallback:** If no confident IGDB match is found, leave `igdb_id` NULL. The game remains as an Xbox-only entry and is silently skipped by the store availability pass until a future sync resolves the match.

---

### 4. Store Availability

No changes to the `store_availability` table or population strategy. All Xbox titles with a resolved `igdb_id` are evaluated for Steam and GOG availability on the next availability pass.

---

### 5. Schema Changes

**`achievements` — new columns:**
```sql
ALTER TABLE achievements ADD COLUMN IF NOT EXISTS gamerscore_earned INTEGER;
ALTER TABLE achievements ADD COLUMN IF NOT EXISTS gamerscore_total  INTEGER;
```

`NULL` for all non-Xbox rows. Populated from `stg_xbox_library` during the promote step.

**`library.purchase_source`** — already exists (added during PSN integration). Xbox writes `'unknown'` for all rows — acquisition type is not determinable from the TitleHub API.

**New staging table:** `stg_xbox_library` (defined in §2a above).

**New `platforms` row:** `Xbox` (seeded at init alongside Steam, GOG, and PlayStation).

---

### 6. Schema Summary of New/Changed Objects

| Object | Change |
|---|---|
| `platforms` | New row: `Xbox` (seeded at init) |
| `stg_xbox_library` | New staging table |
| `achievements.gamerscore_earned` | New column — Xbox Gamerscore earned, NULL for other platforms |
| `achievements.gamerscore_total` | New column — Xbox Gamerscore total, NULL for other platforms |
| `library.purchase_source` | Existing column — populated with `'purchased'`/`'subscription'`/`'unknown'` for Xbox rows |

---

### 7. Sync Sequencing

```
collect.py run order:
1. Steam sync (existing)
2. GOG sync (existing)
3. PSN sync (existing)
4. Xbox sync (new) — single library pass; achievement summary included in same response
5. IGDB matching pass (runs after all platforms are staged)
6. Store availability pass (runs after IGDB matching)
```

Idempotency is preserved throughout — all steps use upserts. `gamerscore_earned`, `gamerscore_total`, and `purchase_source` are overwritten on each sync (they reflect current Xbox state). User preferences (`user_game_prefs`) are never touched by the pipeline.

---

### 8. Library UI

**Platform badge:** Xbox games display an Xbox platform badge on their library card, consistent with Steam, GOG, and PlayStation badges.

**Game Pass indicator:** Not implemented — acquisition type cannot be determined from the TitleHub API. All Xbox cards display the platform badge only. This is documented as a known limitation in the User Guide.

**Platform filter:** The library platform filter is driven by the `platforms` table. Because the `Xbox` row is seeded into `platforms` at init (§6), Xbox appears in the filter automatically — no additional UI code is required.

**Disabled Xbox:** If the user disables Xbox via Connected Services ([[US-011: Connected Services Management]]), Xbox games are hidden from the library view while disabled.

---

### 9. Preference Agent Integration

Achievement completion rate and Gamerscore are surfaced to the preference agent as engagement signals alongside Steam achievements and PSN trophy progress.

The agent profile builder (`profile.json`) is updated to include:
- Xbox games in the owned-games list with their platform tag
- Per-game achievement completion rate (`achievements_earned / achievements_total`) as an engagement depth signal
- Per-game `gamerscore_earned` as a secondary engagement signal (higher Gamerscore on a title indicates investment)
- All Xbox titles treated equally by the agent — acquisition type is unknown, so no ownership weighting is applied

---

## Data & Privacy Considerations

- `xbox.client_id`, `xbox.client_secret`, `xbox.access_token`, and `xbox.refresh_token` stored only in `gandalf.json` (gitignored). Never in the database or any committed file.
- `stg_xbox_library` and `platform_games` contain game title data only — no Xbox account identifiers (XUIDs) or personal data beyond the game list.
- The unofficial API ToS risk is personal to this single-account tool; no multi-tenant exposure.

---

## Open Questions

1. **Game Pass detection:** ~~Resolved~~ — `game_pass.is_game_pass` reflects current catalogue availability, not acquisition history. Acquisition type cannot be determined. All Xbox rows use `purchase_source = 'unknown'`. Documented as a known limitation in the User Guide.
2. **Playtime:** ~~Resolved~~ — confirmed absent from the TitleHub response model. Not stored. Engagement signals are achievement completion rate and Gamerscore only.
3. **IGDB Xbox category:** Confirm correct `category` values for Xbox One and Xbox Series titles in the IGDB `external_games` schema before coding the matching pass. *To be confirmed during implementation.*
4. **Achievement data for lapsed Game Pass titles:** Confirm whether the TitleHub response continues to include achievement summary data after Game Pass access lapses. *To be confirmed once authentication is established.*
