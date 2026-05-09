---
title: "Guide: Steam Achievement Detail"
date: 2026-05-09
tags: [user-guide, steam, achievements, detail-page]
story: "[[US-026: Steam Achievement Detail]]"
---

## Overview

The Steam tab on the game detail page shows a full achievement grid — one icon per achievement, full-colour if unlocked and greyed-out if locked, with name and unlock date on hover.

## Prerequisites

- Steam library synced
- Steam **Profile** and **Game details** privacy settings set to **Public** (required for achievement data — see [[Guide-Steam-Auth-And-Library]])

## Step-by-Step

### 1. Sync achievements

From the library page or logs page, click **Sync Now → Steam › Achievements**, or run:

```bash
python src/collect.py --platforms steam:achievements
```

The sync runs two passes per game:
1. **`GetPlayerAchievements`** — fetches your unlocked/locked status and unlock timestamps
2. **`GetSchemaForGame`** — fetches achievement names, descriptions, and icon URLs (public API, no privacy restriction)

The log reports how many games have achievement data and how many schema calls were made.

### 2. View on the detail page

Open any Steam game detail page. On the **STEAM** tab:

- The summary line (`30 / 94 · 32%`) is always shown when achievement data exists
- Below it, the achievement grid shows all achievements for the game
- **Unlocked** achievements appear first with their full-colour icon
- **Locked** achievements appear after with their greyed-out icon
- Hover any icon to see the achievement name, description, and unlock date (if unlocked)

### 3. Re-syncing

Running **Steam › Achievements** again upserts all data — counts and individual achievement rows are refreshed. No data is lost on re-run.

## Troubleshooting

**Achievement grid missing, only the summary shows**
: The schema fetch hasn't run yet, or `GetSchemaForGame` returned no data for this game. Re-run **Steam › Achievements** — the schema pass runs automatically. Some games have achievements but no schema page on Steam; in that case the grid will remain absent.

**0 games have achievement data**
: Your Steam **Profile** or **Game details** is set to Private. Set both to Public in Steam → Edit Profile → Privacy Settings, sync, then set back to Private if desired.

**Icons not loading**
: Icons are served directly from Steam's CDN (`steamcdn-a.akamaihd.net`). Check your network connection or try reloading the page.
