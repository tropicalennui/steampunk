---
title: "Guide: Game Detail View & Unmerge"
date: 2026-05-09
tags:
  - user-guide
  - library
  - detail-view
  - unmerge
  - merge
story: "[[US-015-Game-Detail-View-And-Unmerge]]"
---

## Overview

Every game card in your library links to a full-page detail view showing all platform data held for that game in one place. If the game was created by merging two entries you can separate them back into independent cards from the same page.

## Prerequisites

- Logged in to SteamPunk
- At least one game in your library (run a sync if the library is empty)

## Step-by-Step

### Opening the detail view

Click anywhere on a game card **except** the action buttons (thumbs up/down, hide). The browser navigates to `/library/games/{id}`. Use the browser back button or the **← Library** breadcrumb to return.

### Reading platform data

Tabs appear for each platform the game is owned on (Steam, PSN, GOG, Switch). Click a tab to switch between them.

| Tab | What you'll see |
|---|---|
| **Steam** | Playtime, last/first played, achievements, release date, categories, your review |
| **PSN** | Trophy progress, trophies earned/defined, PS4/PS5 flag, acquisition type |
| **GOG** | Release date, purchase date |
| **Switch** | Playtime |

Store availability badges (**On Steam** / **On GOG**) appear in the header when the game is listed on a store you don't currently own it on.

Genres and tags appear at the bottom of the page, sourced from Steam metadata.

### Changing your rating or hiding a game

The **Liked / Disliked** and **Hide from library** buttons in the header work the same as on the library grid. Changes take effect immediately without a page reload.

### Unmerging a merged game

If the **Merged entries** section appears at the bottom of the page, one or more games were absorbed into this card via drag-to-merge.

1. Review the listed entries and their platform badges to confirm which is which.
2. Click **Unmerge** next to the entry you want to restore as a separate card.
3. Confirm the prompt: *"Restore [title] as a separate card?"*
4. The page reloads. The entry disappears from the Merged entries list (or the section disappears entirely if it was the only one) and the game reappears as its own card in the library grid.

You can unmerge one entry at a time if there are multiple.

## Troubleshooting

**Page shows 404 — "Game not found"**
You navigated to the URL of a game that was merged into another. The merged-away entry no longer has its own page. Find it via the Merged entries section on the canonical game's detail page.

**Unmerge button fails with an error**
The entry may already have been unmerged in another tab. Refresh the page to see the current state.

**No platform tabs appear**
The game exists in the `games` table but has no library entries linked to it — this can happen after an interrupted sync. Re-run the relevant platform sync.
