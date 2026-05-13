---
title: "US-001: Steam Auth & Library Viewer"
date: 2026-05-01
tags: [user-story, steam, auth, library, web-app]
status: done
---

## As a...
A Steam user running this tool locally

## I want to...
Log in with my Steam account via a browser, and then browse my full game library — with playtime and genres — in a clean web interface

## So that...
I have a private, locally-hosted view of my Steam data without needing to expose my Steam profile to the public

## Acceptance Criteria

### Authentication
- [x] App presents a "Login with Steam" page as the entry point
- [x] Login uses Steam OpenID 2.0 — no username/password handled by the app
- [x] On successful login, a signed server-side session is created
- [x] Unauthenticated requests to any route redirect to the login page
- [x] Logout clears the session and returns to the login page

### Navigation
- [x] A dropdown menu in the top-right of every authenticated page contains: User Profile, Games List, Logout
- [x] Menu shows the user's Steam avatar and display name when logged in

### Games List page
- [x] Displays all owned games with: name, total playtime (hours), genres
- [x] Games with zero playtime are visually distinguished (never launched)
- [x] Page is searchable / filterable by genre

### User Profile page
- [x] Shows Steam display name, avatar, and account summary
- [x] Shows high-level library stats: total games, total hours played, top 5 genres by playtime

### Data pipeline
- [x] `collect.py` fetches library + store metadata using the authenticated user's SteamID64
- [x] Enriched data is saved to `data/library.json` (gitignored) — moved to [[US-006: Library JSON Export]]
- [x] Pipeline can be re-run with `--refresh` to update data — moved to [[US-007: Pipeline Refresh Flag]]

## Out of Scope (for now)
- Friends / social data
- Price filtering (covered in US-002)
- Agent / recommendations (covered in US-002)
- Tags display and filtering (covered in [[US-005: Game Tags]])
- Library JSON export (covered in [[US-006: Library JSON Export]])
- `--refresh` CLI flag (covered in [[US-007: Pipeline Refresh Flag]])
