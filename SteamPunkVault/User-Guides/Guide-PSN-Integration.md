---
title: "Guide: PSN Integration"
date: 2026-05-03
tags: [user-guide, psn, playstation, library, multi-platform, trophies]
story: "[[US-008: PSN Integration]]"
---

## Overview

This guide covers connecting your PlayStation Network account to SteamPunk, syncing your PS4/PS5 library and trophy data, and reading your PlayStation games in the unified library view.

Authentication uses Sony's NPSSO session token — a read-only credential extracted from your browser while you are logged into PlayStation.com. Your PSN password is never seen or stored.

---

## Prerequisites

- SteamPunk is running and you are logged in via Steam
- You have a PlayStation Network account with PS4 or PS5 games
- You are able to log into [playstation.com](https://www.playstation.com) in your browser
- *(Optional)* An IGDB API key is configured in `gandalf.json` — required for cross-platform game matching and store availability badges (see [[Guide: GOG Integration & Normalised Multi-Platform Library]])

---

## Step-by-Step

### 1. Retrieve your NPSSO token

The NPSSO token is a session credential that Sony sets in your browser when you log into PlayStation.com. It is valid for approximately 60 days.

1. Open [playstation.com](https://www.playstation.com) in your browser and sign in if you aren't already
2. In the same browser, navigate to:
   ```
   https://ca.account.sony.com/api/v1/ssocookie
   ```
3. You will see a short JSON response:
   ```json
   {"npsso":"<64-character token>","expires_in":5000000}
   ```
4. Select all and copy the entire response — SteamPunk will extract the token automatically

> **Do this and connect immediately.** The NPSSO exchange happens at connection time — if you leave a long gap the session may have changed.

---

### 2. Connect your PlayStation account

1. Click your avatar in the top-right corner and select **Setup**
2. Click the **PlayStation** tab
3. Click **Open Token Page ↗** — this opens the NPSSO endpoint in a new browser tab (you must already be logged into PlayStation.com)
4. Select all, copy the JSON response
5. Return to the SteamPunk Setup tab, paste into the token field, and click **Connect**
6. A green confirmation banner appears, showing the token expiry date

> Your NPSSO and OAuth tokens are stored in `gandalf.json` (gitignored, never committed). SteamPunk exchanges the NPSSO for OAuth access and refresh tokens automatically on first sync, and refreshes them silently going forward.

---

### 3. Sync your PlayStation library

From the **Games Library** page, click the **Sync Now** button to sync all platforms, or click the **▾** chevron to select a specific platform:

| Option | What it does |
|---|---|
| **All platforms** | Fetches Steam + GOG + PSN libraries, then runs IGDB matching and store availability checks |
| **PlayStation only** | Refreshes PSN library and trophy data only |

The sync runs in the background. Click **Sync Logs** in the nav to watch progress.

**What gets synced:**
- All games where you have earned at least one trophy (PS4 and PS5)
- Trophy completion percentage per game (stored as an engagement signal alongside Steam achievement data)

> **Library coverage note:** The PSN API surfaces games via trophy activity. Games you own but have never launched (zero trophies) will not appear. This is a known limitation of the unofficial API and will be confirmed during first sync.

---

### 4. Reading the unified library

PlayStation games appear in the library alongside Steam and GOG titles:

| Badge | Meaning |
|---|---|
| `PS` (blue) | Owned on PlayStation Network |
| `×2` / `×3` (amber) | Owned on more than one platform |
| `On Steam` | Not owned on Steam, but available to buy there |
| `On GOG` | Not owned on GOG, but available to buy there |

**Playtime** is not available for PSN games — Sony does not expose playtime via its API. **Trophy completion %** is shown instead where available, and is used by the preference agent as an engagement signal equivalent to Steam achievement rate.

---

### 5. Reconnecting when the token expires

The NPSSO token is valid for approximately 60 days. The Setup page shows the expiry date under the connected indicator. When it expires:

1. A warning banner appears on **Setup → PlayStation**
2. Repeat the steps in §1 and §2 above to retrieve a fresh token and reconnect
3. Run a sync — the pipeline will exchange the new NPSSO for fresh OAuth tokens automatically

> OAuth access and refresh tokens are refreshed automatically throughout the token's lifetime. You only need to reconnect when the NPSSO itself expires.

---

## Troubleshooting

**"PSN session expired — reconnect via Setup page" in sync logs**
Navigate to Setup → PlayStation and reconnect with a fresh NPSSO token.

**"PSN not connected" in sync logs**
The `psn.npsso` field is missing from `gandalf.json`. Connect via the Setup page.

**"No auth code in redirect" in sync logs**
The NPSSO was rejected by Sony — likely because your PlayStation.com session had ended before you retrieved the token. Log into playstation.com again and repeat §1–2 immediately.

**0 PSN titles found after a successful sync**
Your PSN account has no trophy activity. Games must have at least one trophy earned to appear via the API.

**PlayStation games appear but have no store availability badges**
IGDB credentials are not configured. Add `igdb.client_id` and `igdb.client_secret` to `gandalf.json` and run a full sync.

**Fewer titles than expected**
Only games with trophy activity are returned. Games you own but have never played will not appear.
