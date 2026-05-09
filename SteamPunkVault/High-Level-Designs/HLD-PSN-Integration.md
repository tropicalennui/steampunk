---
title: "HLD: PSN Integration"
date: 2026-05-03
tags: [hld, psn, playstation, library, multi-platform, trophies]
story: "[[US-008: PSN Integration]]"
status: implemented
---

## Overview

Extend the multi-platform library pipeline to ingest the user's PlayStation Network (PSN) game library and trophy data alongside Steam and GOG. PSN entries are deduplicated against existing titles via IGDB and merged into the canonical `games` table. Trophy completion rates feed the preference agent as an engagement signal equivalent to Steam achievement rates. PS Plus subscription titles are included but tagged to distinguish them from purchased games.

## Goals & Non-Goals

**Goals**
- Authenticate with PSN using the NPSSO cookie flow and persist OAuth tokens in `gandalf.json`
- Sync the user's PSN game library (purchased + PS Plus) into `stg_psn_library`
- Promote staged games into `platform_games` under a `PlayStation` platform row
- Sync per-game trophy completion % and store it as a preference-agent signal
- Link PSN titles to canonical `games` rows via IGDB matching (deduplicating cross-platform titles)
- Surface cross-platform store availability badges for PlayStation-owned games

**Non-Goals**
- Friends / social / activity feed data
- PlayStation Store price lookups
- PS3 / Vita / PSP legacy library (PS4/PS5 titles only)
- Per-trophy detail (individual trophies, timestamps) — summary stats only

---

## Design

### 1. PSN Authentication

Sony does not offer a public OAuth2 client registration for personal data access. The community `psnawp` Python library wraps the unofficial PSN web API using a short-lived NPSSO session cookie as the entry credential.

**Flow:**
1. User logs into `https://www.playstation.com` in their browser
2. User retrieves their NPSSO token from `https://ca.account.sony.com/api/v1/ssocookie` (a JSON endpoint that returns the token while logged in)
3. User pastes the token into the SteamPunk Setup page
4. App calls `psnawp`'s auth exchange, which POSTs the NPSSO to Sony's OAuth endpoint and receives `access_token` + `refresh_token`
5. Tokens stored in `gandalf.json` under `psn.npsso`, `psn.access_token`, `psn.refresh_token`, `psn.expires_at`

**Token refresh:** `collect.py` checks `psn.expires_at` before each PSN API call and refreshes proactively if within 60 seconds of expiry using `psnawp`'s built-in refresh flow.

**Expired / revoked token:** If the refresh request fails, `collect.py` logs the error, skips the PSN sync for that run, and sets `psn.auth_expired = true` in `gandalf.json`. The Setup page reads this flag and displays a "Reconnect PlayStation" prompt. The flag is cleared on successful re-authentication.

**Credentials:** `psn.npsso`, `psn.access_token`, `psn.refresh_token` stored only in `gandalf.json` (gitignored). Never committed, never in the database.

**ToS note:** This flow uses an unofficial API that violates Sony's Terms of Service. Risk of account action is low at personal-use request rates, but the pipeline must apply conservative rate limiting (see §2).

### 2. PSN Library & Trophy Sync

**Library completeness caveat:** The PSN API does not expose a clean owned-games entitlement list equivalent to Steam's or GOG's. What is reliably available is the user's trophy title list — every game where at least one trophy has been earned. Games played without earning any trophy may not appear. This is a known limitation of the unofficial API; the actual coverage will be confirmed empirically during implementation.

**PS Plus:** PS Plus catalogue games appear in the same trophy title list. They are identified by the `productId` prefix conventions used by PSN (varies by region/era). Where psnawp exposes an `isPS Plus` or equivalent flag, use it. Otherwise, tag the source as `subscription` when the acquisition type can be inferred; fall back to `unknown` when it cannot.

**psnawp calls:**
- `PSNAWP.user(online_id="me").trophy_titles()` — paginated list of all games with trophy activity; each entry includes `np_communication_id`, `title_name`, `defined_trophies`, `earned_trophies`, `progress` (0–100)
- Platform field on each entry (`PS4` / `PS5`) is used to populate `stg_psn_library.platform`

**Staging table (new):**
```sql
stg_psn_library (
  np_communication_id  VARCHAR PRIMARY KEY,
  title                VARCHAR,
  platform             VARCHAR,         -- 'PS4' or 'PS5'
  acquisition_type     VARCHAR,         -- 'purchased', 'subscription', or 'unknown'
  trophy_progress      INTEGER,         -- 0–100 completion %
  trophies_earned      INTEGER,
  trophies_defined     INTEGER,
  collected_at         TIMESTAMP
)
```

**Rate limiting:** Apply a 0.5 s delay between paginated trophy title requests. The full title list is fetched in one paginated pass per sync run; individual trophy detail calls are not made (summary stats only).

**Promote step:** Upsert from `stg_psn_library` into `platform_games` using `np_communication_id` as `external_id`. The `PlayStation` row in `platforms` is the `platform_id`. Set `acquisition_type` on `platform_games` (see §5 schema change). Trophy completion % is written to `platform_games.trophy_progress`.

### 3. Cross-Platform Game Matching via IGDB

PSN titles are matched to canonical `games` rows using the same IGDB `external_games` strategy established in HLD-003.

**IGDB category for PSN:** `category = 45` (PlayStation Network). Verify against IGDB API docs during implementation — fall back to title-similarity matching if the category lookup yields no result.

**Matching strategy:** identical to HLD-003 §3 — score candidates on title similarity + publisher + release year, accept only above the confidence threshold, log near-misses, flag conflicts for manual review rather than auto-merging.

**Fallback:** If no confident IGDB match is found, leave `igdb_id` NULL. The game remains in the library as a PlayStation-only entry and is silently skipped by the store availability pass until a future sync resolves the match.

### 4. Store Availability

No changes to the `store_availability` table or population strategy from HLD-003 §4. PlayStation-owned games with a resolved `igdb_id` will automatically be evaluated for Steam and GOG availability on the next availability pass.

### 5. Schema Changes

**`platform_games` — new column:**
```sql
ALTER TABLE platform_games ADD COLUMN acquisition_type VARCHAR
  CHECK (acquisition_type IN ('purchased', 'subscription', 'unknown'));
```

This column is `NULL` for all existing Steam and GOG rows (neither platform currently has a subscription distinction). It is populated only for PSN entries at this time but is intentionally platform-agnostic for future use (e.g. Xbox Game Pass).

**`platform_games` — new column:**
```sql
ALTER TABLE platform_games ADD COLUMN trophy_progress INTEGER;
```

Stores the PSN trophy completion % (0–100) for PlayStation entries. `NULL` for Steam and GOG rows. Steam achievement completion rate continues to live in the existing achievements columns — this column is PSN-specific for now.

**New staging table:** `stg_psn_library` (defined in §2 above).

**New `platforms` row:** `PlayStation` (seeded at init alongside Steam and GOG).

### 6. Schema Summary of New/Changed Objects

| Object | Change |
|---|---|
| `platforms` | New row: `PlayStation` (seeded at init) |
| `stg_psn_library` | New staging table |
| `platform_games.acquisition_type` | New column — `purchased`, `subscription`, `unknown`, or NULL |
| `platform_games.trophy_progress` | New column — PSN trophy completion %, NULL for other platforms |

### 7. Sync Sequencing

```
collect.py run order:
1. Steam sync (existing)
2. GOG sync (existing)
3. PSN sync (new)
4. IGDB matching pass (runs after all platforms are staged)
5. Store availability pass (runs after IGDB matching)
```

Idempotency is preserved throughout — all steps use upserts. `acquisition_type` and `trophy_progress` are overwritten on each sync (they reflect current PSN state). User preferences (`user_game_prefs`) are never touched by the pipeline.

### 8. Library UI

**Platform badge:** PSN games display a PlayStation platform badge on their library card, consistent with Steam, GOG, and Nintendo Switch badges.

**Platform filter:** The library platform filter is driven by the `platforms` table (see [[HLD: GOG Integration & Normalised Multi-Platform Library]] §7). Because the `PlayStation` row is seeded into `platforms` at init (§6), PSN appears in the filter automatically — no additional UI code is required.

**Disabled PSN:** If the user disables PlayStation via Connected Services ([[US-011: Connected Services Management]]), the `PlayStation` row is excluded from `GET /platforms?enabled=true` and removed from the filter chip list. PSN games are hidden from the library view while disabled.

---

### 9. Preference Agent Integration

Trophy completion % on PSN entries is surfaced to the preference agent as an engagement signal alongside Steam achievement completion rate. The agent profile builder (`profile.json`) is updated to include:

- PSN games in the owned-games list with their platform tag
- Per-game `trophy_progress` as an engagement depth signal (same role as `achievement_completion_rate` for Steam)
- `acquisition_type = 'subscription'` as a weak ownership signal — PS Plus titles are included in recommendations but weighted slightly lower than purchased titles since access may lapse

---

## Data & Privacy Considerations

- `psn.npsso`, `psn.access_token`, and `psn.refresh_token` stored only in `gandalf.json` (gitignored). Never in the database or any committed file.
- `stg_psn_library` and `platform_games` contain game title data only — no PSN account identifiers or personal data beyond the game list.
- The unofficial API ToS risk is personal to this single-account tool; no multi-tenant exposure.

---

## Open Questions

1. **IGDB PSN category:** ~~Confirm `category = 45`~~ **Resolved:** `IGDB_PSN_CATEGORY = 36` (PlayStation Store US) — confirmed during implementation and set in `collectors/pipeline.py`.
2. **Library completeness:** Empirically verify during implementation whether `trophy_titles()` covers all owned games or only trophy-active ones. If coverage is materially incomplete, evaluate whether PSN purchase history endpoints (less reliable, region-specific) are worth adding.
3. **PS Plus acquisition detection:** Confirm whether `psnawp` exposes a reliable flag for PS Plus vs. purchased titles, or whether heuristics are needed.
