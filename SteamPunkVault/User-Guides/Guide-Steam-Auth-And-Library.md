---
title: "Guide: Steam Auth & Library Viewer"
date: 2026-05-03
tags: [user-guide, steam, auth, library]
story: "[[US-001: Steam Auth & Library Viewer]]"
---

## Overview

SteamPunk is a locally-hosted web app that lets you log in with your Steam account and browse your full game library — complete with playtime, genres, and stats — without making your Steam profile public.

## Prerequisites

- Python 3.11+ installed
- A Steam account
- Your Steam Web API key and SteamID64 stored in `gandalf.json` (see [[Guide-Steam-Session-Cookie]])
- `gandalf.json` at the workspace root with the following keys:
  - `STEAM_API_KEY` — from [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey)
  - `SECRET_KEY` — any long random string used to sign sessions

## Step-by-Step

### 1. Sync your Steam library

Run the data pipeline to fetch your games from Steam before starting the server:

```bash
python src/collect.py --platforms steam
```

This populates the local DuckDB database with your owned games, genres, playtime, and store metadata.

### 2. Start the web server

```bash
python run.py
```

The app starts on `http://localhost:8000` by default.

### 3. Log in with Steam

Open `http://localhost:8000` in your browser. You will see the **Login with Steam** page. Click the button — you will be redirected to Steam's OpenID login. SteamPunk never sees your password.

After authenticating, Steam redirects you back to the app and a signed server-side session is created.

### 4. Browse your library

The **Games List** page (`/library`) shows all your owned games with:

- Game name and cover art
- Total playtime in hours
- Genres

Games you have never launched are shown at reduced opacity with a "Never played" label.

Use the search bar to filter by game name or genre. Platform filters are available if you have connected additional platforms (e.g. GOG).

### 5. View your profile

The **User Profile** page (`/profile`) shows:

- Your Steam display name and avatar
- Total number of owned games
- Total hours played across your library
- Top 5 genres by playtime, displayed as a bar chart

### 6. Log out

Open the dropdown menu in the top-right corner (your avatar and name) and click **Logout**. Your session is cleared and you are returned to the login page.

## Troubleshooting

**"Login with Steam" redirects but fails to return**
: Verify `SECRET_KEY` is set in `gandalf.json`. Without it the session middleware cannot sign the callback state.

**Library page is empty**
: Run `python src/collect.py --platforms steam` first to populate the database.

**Avatar or display name missing in the nav menu**
: Check that `STEAM_API_KEY` in `gandalf.json` is valid. The app fetches your profile from the Steam Web API on login.
