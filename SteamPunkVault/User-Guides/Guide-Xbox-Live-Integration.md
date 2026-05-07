---
title: "Guide: Xbox Live Integration"
date: 2026-05-07
tags: [user-guide, xbox, xbox-live, library, achievements, gamerscore]
story: "[[US-016: Xbox Live Integration]]"
---

## Overview

SteamPunk can connect to your Xbox account and import your game library, achievement progress, and Gamerscore into the unified library view. All Xbox games you have played — whether purchased or accessed through Game Pass — are imported.

## Prerequisites

- A Microsoft / Xbox account
- SteamPunk running locally
- Port 8080 must be free on your machine during the initial connection (SteamPunk uses it briefly to receive Microsoft's auth callback)

## Step-by-Step

### 1. Connect your Xbox account

1. Go to **Setup** in the SteamPunk navigation
2. Click the **Xbox** tab
3. Click **Connect Xbox** — your browser will open a Microsoft login page
4. Sign in with your Microsoft account
5. After signing in, Microsoft redirects your browser automatically — you will be returned to the SteamPunk Setup page with a confirmation that Xbox is connected

> If the connection fails, make sure nothing else is using port 8080 and try again.

### 2. Sync your Xbox library

Once connected, click **Sync Now** on the Xbox tab of the Setup page, or use the **Sync Now → Xbox** option from the library page.

SteamPunk will fetch your full Xbox game history and import it. Syncing typically takes a few seconds.

### 3. View your Xbox games

After a successful sync, Xbox games appear in your library with a green **XBOX** badge. Use the **Xbox** filter pill at the top of the library to view only Xbox titles.

## What is imported

| Data | Imported |
|---|---|
| Game title | Yes |
| Last played date | Yes |
| Achievement count (earned / total) | Yes |
| Achievement completion % | Yes |
| Gamerscore (earned / total) | Yes |
| Playtime | No — not available from the Xbox API |

## Known Limitations

**Game Pass vs purchased titles:** The Xbox API does not expose how a title was acquired. SteamPunk cannot distinguish between games you own outright and games you accessed through a Game Pass subscription. All Xbox titles are treated equally in recommendations. If your Game Pass subscription lapses and you lose access to a title, it will remain in your SteamPunk library as a historical record.

**Playtime:** Microsoft does not expose playtime data through the API used by SteamPunk. Achievement completion rate and Gamerscore are used as engagement signals instead.

**Unofficial API:** SteamPunk uses a community library (`xbox-webapi-python`) to access Xbox data. This is not an officially sanctioned Microsoft API and may change without notice. If a sync stops working after a Microsoft update, check for a new version of `xbox-webapi`.

## Troubleshooting

**"Xbox session expired — reconnect via Setup page"** — Your OAuth tokens have expired. Go to Setup → Xbox and click Connect Xbox to re-authenticate.

**Sync completes but no Xbox games appear** — Check the sync log for errors. If the library is empty immediately after the first sync, the IGDB matching pass may not have run yet (requires IGDB credentials to be configured).

**Port 8080 already in use** — Another application is using port 8080. Stop that application and try connecting again.
