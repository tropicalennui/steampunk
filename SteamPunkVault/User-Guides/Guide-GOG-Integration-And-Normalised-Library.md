---
title: "Guide: GOG Integration & Normalised Multi-Platform Library"
date: 2026-05-03
tags: [user-guide, gog, steam, library, multi-platform, hide]
story: "[[US-003: GOG Integration & Normalised Multi-Platform Library]]"
---

## Overview

This guide covers connecting your GOG account to SteamPunk, running a multi-platform sync, and using the unified library view — including platform filters, cross-platform ownership indicators, store availability badges, and game hiding.

---

## Prerequisites

- SteamPunk is running and you are logged in via Steam
- Your Steam session cookie is already configured (see [[Guide: Steam Session Cookie]])
- You have a GOG account with games in your library
- *(Optional)* An IGDB API key is configured in `gandalf.json` — required for cross-platform game matching and store availability badges

---

## Step-by-Step

### 1. Connect your GOG account

1. Click your avatar in the top-right corner and select **Setup**
2. Click the **GOG** tab
3. Click **Open GOG Login ↗** — this opens the GOG authentication page in a new browser tab
4. Sign in to GOG and approve access when prompted
5. After approving, GOG redirects you to a page at `embed.gog.com`. Copy the **full URL** from your browser's address bar — it will look like:
   ```
   https://embed.gog.com/on_login_success?origin=client&code=XXXXXXXX
   ```
6. Return to the SteamPunk Setup tab, paste the URL into the **Step 2** field, and click **Connect**
7. A green confirmation banner confirms the connection

> Your GOG access and refresh tokens are stored in `gandalf.json` (gitignored, never committed). SteamPunk refreshes the token automatically — you should only need to do this once.

---

### 2. Sync your GOG library

From the **Games Library** page, click the **Sync Now** button to sync all platforms, or click the **▾** chevron to choose a specific platform:

| Option | What it does |
|---|---|
| **All platforms** | Fetches Steam + GOG libraries, then runs IGDB matching and store availability checks |
| **Steam only** | Refreshes Steam library data only |
| **GOG only** | Refreshes GOG library data only |

The sync runs in the background. Click **Sync Logs** in the nav to watch progress.

> **First sync note:** Fetching product details for a large GOG library takes time — roughly 0.5 seconds per game. A 200-game library takes ~2 minutes. Subsequent syncs are faster as only new games need enriching.

---

### 3. IGDB cross-platform matching

If `igdb.client_id` and `igdb.client_secret` are configured in `gandalf.json`, SteamPunk automatically matches games across platforms using the IGDB database after each sync.

When a Steam game and a GOG game are identified as the same title, they are linked to a single canonical entry in the library. This powers:
- Multi-platform ownership display
- Store availability checks

To add IGDB credentials:
1. Create a free Twitch Developer account at [dev.twitch.tv](https://dev.twitch.tv)
2. Register an application and copy the **Client ID** and **Client Secret**
3. Add them to `gandalf.json`:
   ```json
   "igdb": {
     "client_id": "YOUR_CLIENT_ID",
     "client_secret": "YOUR_CLIENT_SECRET"
   }
   ```
4. Run a full sync — IGDB matching runs automatically after the library fetch

> Games that IGDB cannot match (no external ID on record) remain as separate library entries and will not receive store availability badges. This typically affects very old or niche titles.

---

### 4. Reading the unified library

Each game card in the library shows the platforms you own it on:

| Badge | Meaning |
|---|---|
| `STEAM` (blue) | Owned on Steam |
| `GOG` (purple) | Owned on GOG |
| `×2` (amber) | Owned on more than one platform |
| `On Steam` | Not owned on Steam, but available to buy there |
| `On GOG` | Not owned on GOG, but available to buy there |

**Playtime** is shown for Steam games only. GOG-only games show "Playtime unknown" since GOG does not expose playtime via its API.

---

### 5. Filter by platform

Use the filter pills above the game grid to narrow the library:

- **All** — show everything (default)
- **Steam** — show only games you own on Steam
- **GOG** — show only games you own on GOG
- **Multi-platform** — show only games you own on two or more platforms

Platform filters combine with the text search box.

---

### 6. Hide a game

To remove a game from your default library view:

1. Hover over the game card — action buttons appear in the top-right corner
2. Click the **hide** button (👁)
3. The game disappears from the default view immediately

To see hidden games, click **Show hidden** in the top toolbar. Hidden games appear dimmed with a dashed border. To unhide, hover the card and click the hide button again.

> Hiding is stored in the database and persists across syncs. A sync will never un-hide a game you have hidden.

---

### 7. Reconnecting GOG (if session expires)

GOG access tokens are refreshed automatically. If the refresh token itself expires (e.g. after several months without syncing):

1. A warning banner appears on the **Setup → GOG** tab
2. Follow the same steps as the initial connection (Step 1 above) to reconnect

---

## Troubleshooting

**"GOG not connected or auth expired" in sync logs**
Navigate to Setup → GOG and reconnect your account.

**GOG games appear but have no platform badges or store availability**
IGDB credentials are not configured. Add `igdb.client_id` and `igdb.client_secret` to `gandalf.json` and run a full sync.

**Fewer GOG products than expected were fetched**
The GOG product details API occasionally returns no data for older or region-restricted titles. The product ID is still staged; the library entry will have a blank title until GOG's API returns data on a future sync.

**The GOG login page says "redirect URI mismatch"**
This should not happen with the current setup. If it does, ensure `gandalf.json` contains the correct community `client_id` (`46899977096215655`).
