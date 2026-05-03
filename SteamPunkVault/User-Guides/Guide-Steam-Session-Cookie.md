---
title: "Guide: Steam Session Cookie Setup"
date: 2026-05-01
tags: [user-guide, steam, setup, auth]
story: "[[US-001: Steam Auth & Library Viewer]]"
---

## Overview

SteamPunk uses your Steam session cookie to fetch your private library data without requiring your Steam profile to be set to public. The cookie is stored locally in `gandalf.json` and is **only ever used for read-only GET requests** — it is never used to perform any action on your Steam account.

## When You Need This

- First time setting up SteamPunk
- After your Steam session expires (usually several months)
- If syncing returns an empty library

## Prerequisites

- You must be logged into Steam in the browser you're using

## Step-by-Step

### 1. Log in via SteamPunk

Visit `http://localhost:8000` and click **Sign in through Steam**. After authenticating, you'll be redirected automatically to the setup page.

### 2. Open Browser DevTools

| OS | Shortcut |
|---|---|
| Windows / Linux | `F12` |
| Mac | `⌘ + Option + I` |

### 3. Find the steamLoginSecure Cookie

**Chrome / Edge:**
1. Click the **Application** tab
2. In the left sidebar, expand **Cookies**
3. Click **https://steamcommunity.com**
4. Find the row named **steamLoginSecure**
5. Click it and copy the full **Value**

**Firefox:**
1. Click the **Storage** tab
2. Expand **Cookies**
3. Click **https://steamcommunity.com**
4. Find **steamLoginSecure** and copy the **Value**

The value is a long string beginning with your SteamID64 followed by `%7C%7C` and a long token, e.g.:
```
76561198072286781%7C%7CeyAidHlwZSI6ICJKV1Qi...
```

### 4. Paste and Save

Paste the value into the text area on the setup page and click **Save & Continue**. SteamPunk will validate the cookie immediately — if it works, you'll be taken to your library.

## Security Notes

- The cookie is stored in `gandalf.json` at the workspace root, which is gitignored
- It is only sent in GET requests to `api.steampowered.com`, `store.steampowered.com`, and `steamcommunity.com`
- It is never sent to any other service
- If you're concerned, you can revoke it by logging out of Steam on all devices (Steam → Settings → Security → Deauthorize all other devices)

## Troubleshooting

**"That cookie didn't work" error**
- Make sure you copied the value from `steamcommunity.com`, not `store.steampowered.com`
- Make sure you copied the entire value — it can be very long
- Try logging out and back into Steam in your browser, then copy the fresh cookie

**Library shows empty after sync**
- Your session may have expired — go to `/setup` to paste a new cookie
- Check that `gandalf.json` contains `steam.session_cookie` with a non-empty value

## Refreshing the Cookie

Steam session cookies last several months. When yours expires, the sync will silently return an empty library. Navigate to `http://localhost:8000/setup` at any time to paste a fresh cookie.
