---
title: "HLD: Steam Access Token Auth"
date: 2026-05-09
tags: [hld, steam, auth, achievements, privacy]
story: "[[US-024: Steam Access Token Auth]]"
status: approved
---

## Overview

Extract the JWT from the `steamLoginSecure` session cookie already stored in `gandalf.json` and use it as `access_token` in Steam Web API calls. This authenticates as the profile owner, bypassing Game details privacy restrictions for achievement data.

## Goals & Non-Goals

**Goals**
- Achieve working achievement sync for private profiles using existing credentials.
- Minimal change — no new credential types, no new setup wizard steps, no new token storage.

**Non-Goals**
- Token refresh — access token lifetime matches the session cookie; same renewal process.
- Applying access token auth to other Steam calls (library, wishlist, app details).

## Design

### 1. Token extraction

The `steamLoginSecure` cookie value has the format:

```
{steamid64}||{url_encoded_jwt}
```

Extraction:

```python
def _extract_steam_access_token(session_cookie: str) -> Optional[str]:
    if not session_cookie or "||" not in session_cookie:
        return None
    _, _, token_part = session_cookie.partition("||")
    return urllib.parse.unquote(token_part) if token_part else None
```

### 2. Access token API call

A separate lightweight request (no shared session, no `key` param):

```python
def _fetch_achievements_by_token(access_token, steam_id, app_id):
    resp = requests.get(
        f"{STEAM_API}/ISteamUserStats/GetPlayerAchievements/v1/",
        params={"access_token": access_token, "steamid": steam_id, "appid": app_id},
        timeout=10,
    )
    # parse identical to existing Web API response
```

### 3. Call order in `fetch_achievements`

```
1. access_token present?
   └─ yes → _fetch_achievements_by_token()
      ├─ result → return it
      └─ None (expired / rejected) → fall through
2. _fetch_achievements_community()   ← community XML (no-op for now, kept as hook)
3. Web API with key                  ← works only if profile is public
4. None → no achievement data for this game
```

### 4. Logging

If the access token call returns `success: false` for every game, emit one warning:
```
  WARN: access token rejected — achievement sync requires public Game details
```

### 5. Debug logging removal

The `_ACH_DEBUG_PRINTED` global and associated print statement are removed once the access token path is confirmed working.

## Data & Privacy Considerations

- The JWT is already stored in `gandalf.json` as part of `steam.session_cookie`. No new credential storage required.
- The JWT is short-lived (tied to the Steam session). No long-term credential risk beyond what already exists.
- The `access_token` param is sent over HTTPS to `api.steampowered.com`.

## Open Questions

1. Does `GetPlayerAchievements/v1/` accept `access_token` in place of `key` for private profiles? This is the central assumption — to be confirmed by the first sync run after implementation.
