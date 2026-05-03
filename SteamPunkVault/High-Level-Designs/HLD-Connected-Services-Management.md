---
title: "HLD: Connected Services Management"
date: 2026-05-03
tags: [hld, settings, services, setup, platforms, ui]
story: "[[US-011: Connected Services Management]]"
status: draft
---

## Overview

Add a Connected Services section to the existing `/preferences` page, visually separated from other settings. All supported platforms appear as toggleable cards. Enabling a platform launches its setup flow inline. Disabling prompts the user to either retain their collected data (sync paused, games hidden) or scrub it (platform-specific data deleted, shared canonical data preserved). The enabled/disabled state is persisted in `gandalf.json` and read by `collect.py` before each sync run.

## Goals & Non-Goals

**Goals**
- Give users a single place to see which platforms are linked and which are not
- Allow platforms to be enabled or disabled (at least one must remain enabled at all times); disabling always scrubs collected PII for that platform
- Deep-link the enable toggle directly into each platform's setup flow
- Have `collect.py` respect the enabled set — skip disabled platforms even on manual/force syncs
- Preserve backward compatibility: users with existing credentials are not disrupted

**Non-Goals**
- Per-platform sync scheduling or frequency controls
- Multiple accounts per platform
- Redesigning the individual setup flows themselves (those remain as-is; this story only changes the container/navigation)

---

## Design

### 1. Enabled/Disabled State Storage

Connection state is already tracked in `gandalf.json` per platform. Enabled/disabled state is added to the same structure as a new `enabled` boolean key per platform block.

**`gandalf.json` additions:**

```json
{
  "steam":  { "enabled": true,  ... },
  "gog":    { "enabled": true,  ... },
  "psn":    { "enabled": false, ... },
  "switch": { "enabled": false, ... }
}
```

**Default resolution (backwards compatibility):** If an `enabled` key is absent (existing installs):
- Platform has credentials present → treat as `enabled = true` (**Enabled & Connected**)
- Platform has no credentials → treat as `enabled = false` (**Disabled**)

This means existing users with Steam + GOG connected see no change after the upgrade.

**Rationale for `gandalf.json` over DB:** All platform configuration already lives there. Adding a DB column for a single boolean that belongs conceptually alongside credentials would split the concern for no gain. The DB remains the source of truth for game data only.

### 2. Platform State Model

Each platform has exactly one of three states at any moment:

| State | Condition | UI label |
|---|---|---|
| **Enabled & Connected** | `enabled = true` AND credentials present AND not `auth_expired` | Green dot — Connected |
| **Enabled – Setup Required** | `enabled = true` AND (credentials missing OR `auth_expired`) | Amber dot — Setup required |
| **Disabled** | `enabled = false` | Grey — Disabled |

State is computed in the route handler from `gandalf.json` on every page load — no separate state field needed.

### 3. Connected Services Section in `/preferences`

A "Connected Services" section is added to the existing `/preferences` page, separated from other settings by a divider and section heading. The `/setup` route is unchanged — it remains reachable from the nav dropdown for direct access to individual platform setup flows.

**Section structure within `/preferences`:**

```
/preferences
├── [existing settings — e.g. timezone]
├── ── divider ──
├── Section heading: "Connected Services"
├── Subtitle: "Enable the platforms you use. Disabled platforms are excluded from sync."
└── Platform cards (one per supported platform, in order: Steam, GOG, PlayStation, Nintendo Switch)
    ├── Platform icon + name
    ├── State indicator (coloured dot + label)
    ├── Toggle (enable / disable)
    └── CTA button (context-sensitive — see §4)
```

**Card CTA logic:**

| State | Button label | Action |
|---|---|---|
| Enabled & Connected | Reconnect | Expands the setup section for that platform inline |
| Enabled – Setup Required | Set up | Expands the setup section for that platform inline (auto-opened on page load if only one such platform exists) |
| Disabled | — | No CTA while disabled; toggle enables and reveals Set up |

Each platform's setup section (credential form / OAuth instructions) is rendered below its card and hidden by default via CSS. Toggling to Enabled, or clicking Set up / Reconnect, expands it with a smooth accordion reveal. This replaces the tab mechanism — all platforms remain on one page, only one setup section is open at a time.

### 4. Enable / Disable Flow

**Enabling (Disabled → Enabled – Setup Required):**
1. User flips toggle ON
2. `POST /services/{platform}/enable` — sets `{platform}.enabled = true` in `gandalf.json`; returns updated state
3. Client expands the setup section for that platform (accordion open)
4. No page reload required

**Completing setup:**
- User completes the existing credential/auth flow for that platform (no changes to those flows)
- On success, the card state updates to **Enabled & Connected** (the setup section collapses)

**Abandoning setup:**
- User closes the accordion without completing setup
- State remains **Enabled – Setup Required** (enabled flag is already set)
- On next page load, the card shows the amber dot and Set up CTA

**Disabling (Enabled → Disabled):**
1. User flips toggle OFF
2. If this is the last enabled platform, the toggle is blocked and a message is shown: "At least one service must remain connected."
3. Otherwise, a confirmation modal appears:
   > "Disable [Platform]? All data collected from this service will be permanently deleted. Data for games you also own on other services is preserved. This cannot be undone."
4. User confirms (or cancels, leaving the toggle on)
5. `POST /services/{platform}/disable` — sets `{platform}.enabled = false` and triggers the data scrub operation (see §4a); returns updated state
6. Card collapses to disabled state; no page reload required

### 4a. Data Scrub Operation

Disabling always triggers a scrub. The following is executed server-side within a single transaction:

1. Identify all `platform_games` rows for this platform (`platform_id` = the disabled platform)
2. For each affected `game_id`, check whether any other `platform_games` row references that same `game_id`
   - **Other platform owns it:** delete only the platform-specific `platform_games` row; the canonical `games` row, `user_game_prefs`, and `store_availability` entries are untouched
   - **No other platform owns it:** delete the `platform_games` row, the `store_availability` rows for that `game_id`, the `user_game_prefs` row for that `game_id`, and the `games` row itself
3. Truncate the platform's staging table (`stg_{platform}_library`)
4. Clear platform credentials from `gandalf.json` (`{platform}.access_token`, `{platform}.refresh_token`, `{platform}.npsso`, etc. — whichever apply) while leaving the `enabled: false` flag in place

The scrub is not reversible. A re-enable + re-sync is required to restore the data.

### 5. New API Endpoints

Two new POST endpoints (AJAX, JSON response):

```
POST /services/{platform}/enable
POST /services/{platform}/disable
```

`platform` is validated against the set of known slugs (`steam`, `gog`, `psn`, `switch`). Both endpoints write `{platform}.enabled` in `gandalf.json` and return the computed state for that platform:

```json
{ "platform": "gog", "state": "setup_required" }
```

State values: `"connected"`, `"setup_required"`, `"disabled"`.

The existing `/auth/{platform}/disconnect` endpoints are unchanged. Disconnecting a platform (removing credentials) leaves `enabled = true` — the platform transitions to **Enabled – Setup Required** rather than **Disabled**. Disabling is a separate, explicit user action.

### 6. Library UI — Disabled Platform Filtering

Because disabling always scrubs data (§4a), there is nothing to filter. The relevant `platform_games` rows are deleted at disable time; they are naturally absent from library queries. Disabled platforms do not appear in the platform filter pill.

**Preference agent:** `profile.json` is rebuilt on each sync run. A disabled platform's data is gone until re-enabled and re-synced.

### 7. `collect.py` Integration

Before each platform's sync block, `collect.py` reads `{platform}.enabled` from `gandalf.json` (defaulting per §1 rules if absent). If `enabled = false`, that platform's sync is skipped with a log line:

```
[INFO] PSN sync skipped — platform disabled in settings
```

The enabled flag is authoritative — no runtime override can force a sync for a disabled platform. If the `platforms` parameter passed to `collect.py` includes a disabled platform, that platform is silently skipped.

### 8. Navigation

No nav changes. The Connected Services section appears within the existing `/preferences` page, which is already linked in the user dropdown. `/setup` remains separately accessible from the dropdown for direct platform setup access.

### 9. New Platform Addition Pattern

When a new platform is added (e.g. Nintendo Switch via US-010):
1. Add its slug to the known platform set used in the route validator
2. Add a card template for it in `setup.html` (icon, name, setup section)
3. Seed a row in the `platforms` table
4. Its default state on existing installs is **Disabled** (no `enabled` key, no credentials)

No schema changes are needed to support new platforms under this design.

---

## Data & Privacy Considerations

- `enabled` flags are stored in `gandalf.json` (gitignored). They are not sensitive but belong there for consistency with the rest of the platform config.
- Disabling always scrubs collected PII for that platform. The scrub is irreversible — re-enabling requires re-authentication and a fresh sync.
- Scrub preserves any game data still referenced by another enabled platform — no cross-platform data loss.

---

## Open Questions

None outstanding.
