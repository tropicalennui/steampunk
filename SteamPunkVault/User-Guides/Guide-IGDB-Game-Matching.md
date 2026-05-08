---
title: "Guide: IGDB Game Matching"
date: 2026-05-09
tags: [user-guide, igdb, matching, cross-platform, store-availability]
story: "[[US-019: IGDB Game Matching]]"
---

## Overview

SteamPunk uses IGDB (Twitch's game database) to match games across your platforms and check store availability. Once configured, it can tell you which of your Steam games are also on GOG, and vice versa.

## Prerequisites

- At least one platform library synced (Steam, GOG, or PSN).
- A free Twitch developer account.

## Step-by-Step

### 1. Register a Twitch Application

1. Go to `dev.twitch.tv/console` and log in (create a free Twitch account if needed).
2. Click **Register Your Application**.
3. Fill in the form:

   | Field | Value |
   |---|---|
   | Name | SteamPunk (or any name) |
   | OAuth Redirect URLs | `https://localhost` |
   | Category | Analytics Tool |
   | Client Type | **Confidential** |

   > The redirect URL is a required placeholder — IGDB uses the Client Credentials grant, so no browser redirect ever occurs.

4. Click **Create**.

### 2. Get Your Credentials

1. On the application page, copy the **Client ID**.
2. Click **New Secret** to generate a **Client Secret** — copy it immediately (it won't be shown again).

   > The Client ID is a random alphanumeric string like `abc123xyz789` — not your email address.

### 3. Add Credentials to gandalf.json

Open `gandalf.json` at the workspace root and add the `igdb` section:

```json
{
  "igdb": {
    "client_id": "paste-your-client-id-here",
    "client_secret": "paste-your-client-secret-here"
  }
}
```

### 4. Run the IGDB Sync

**Recommended order — first time setup:**
1. Run a full sync first (**Sync Now**) to populate all platform libraries.
2. Then run IGDB separately from the dropdown: click the **▼** next to Sync Now and select **IGDB / Twitch**.

**On subsequent syncs:**
- **Sync Now** runs everything including IGDB automatically.
- Use the **IGDB / Twitch** dropdown option any time you want to re-run matching and availability checks without re-fetching your platform libraries.

### 5. What to Expect

The sync log will show progress:

```
Fetching IGDB token...
Running IGDB matching pass...
  316 platform_games need IGDB lookup
  104 games matched to IGDB (66 not found in IGDB)
Running store availability pass...
  173 store availability checks to run
All done.
```

- **Matched** — game linked to IGDB; store availability will be checked.
- **Not found** — IGDB has no record for this title (common for obscure or region-specific games). These are skipped silently and retried on the next sync.
- **Store availability checks** — how many games were checked for cross-platform availability.

## Troubleshooting

**"IGDB credentials not configured"**
The `igdb` key is missing or empty in `gandalf.json`. Re-check Step 3.

**"Could not obtain IGDB token"**
The client ID or secret is incorrect, or the Twitch API is unreachable. Verify your credentials at `dev.twitch.tv/console` and check your network connection.

**0 games matched after a full sync**
Most likely the platform libraries are empty. Run a full **Sync Now** first to populate platform data, then run **IGDB / Twitch** separately.

**SSL handshake hangs on first run**
Windows + Python can be slow on the first HTTPS connection to `id.twitch.tv`. Wait 10–15 seconds before assuming it is stuck. You can verify connectivity with:
```powershell
Invoke-WebRequest https://id.twitch.tv
```
A `404` response confirms the network path is open.
