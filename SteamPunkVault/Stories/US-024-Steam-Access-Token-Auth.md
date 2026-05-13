---
title: "US-024: Steam Access Token Auth"
date: 2026-05-09
tags: [user-story, steam, auth, achievements, privacy]
status: superseded
---

## As a...
A privacy-conscious gamer using SteamPunk who keeps their Steam profile private

## I want to...
Have my Steam achievement data synced without being forced to make my Game details public

## So that...
I can use the app as intended without compromising my Steam privacy settings

---

## Background

The Steam Web API (`GetPlayerAchievements`) respects profile privacy settings and returns `success: false` for private profiles, even when called with the profile owner's own API key. A Steam Community XML approach was attempted but no per-user XML achievement endpoint exists.

Steam's newer auth system uses JWTs (JSON Web Tokens) as access tokens. The `steamLoginSecure` session cookie the user already stores in `gandalf.json` contains a URL-encoded JWT in the format `{steamid}||{jwt}`. This JWT can be passed as `access_token=<jwt>` to Steam Web API calls, authenticating as the profile owner and bypassing privacy restrictions.

## Acceptance Criteria

- [ ] A JWT access token is extracted from the `steamLoginSecure` cookie value at the start of each achievement sync
- [ ] `GetPlayerAchievements` is called with `access_token=<jwt>` (no `key` param) when a valid token is available
- [ ] Achievement data is returned for private profiles when the session cookie is present and valid
- [ ] If no session cookie is configured, or the token is rejected, the sync falls back to the existing API key approach and logs a clear warning
- [ ] The debug logging added during investigation is removed

---

## Out of Scope
- Implementing a token refresh flow — the access token lifecycle is tied to the session cookie, which the user already manages
- Extending access token auth to other Steam API calls beyond achievements
