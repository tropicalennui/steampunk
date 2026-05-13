---
title: "US-004: Game Ratings"
date: 2026-05-03
tags: [user-story, ratings, library]
depends-on: "[[US-003: GOG Integration & Normalised Multi-Platform Library]]"
status: merged
---

## As a...
A user with a populated multi-platform games library

## I want to...
Rate any game in my library thumbs up or thumbs down, and filter my library by rating

## So that...
I can quickly surface games I know I enjoy, and separate them from games I've tried and didn't like

## Acceptance Criteria

### Rating a Game
- [x] User can rate any game thumbs up or thumbs down via a single click on the game card
- [x] Clicking the active rating again clears it (toggle behaviour)
- [x] Rating is stored per canonical game in the database (`user_game_prefs.rating`)
- [x] Rating applies across platforms — rating a Steam copy also rates the linked GOG copy
- [x] Rating state is reflected immediately in the UI (optimistic update)

### Filtering by Rating
- [ ] Games List can be filtered to show only liked games (thumbs up)
- [ ] Games List can be filtered to show only disliked games (thumbs down)
- [ ] Rating filter combines with the existing platform filter and text search

## Out of Scope (for now)
- Numeric or star ratings (thumbs up/down is sufficient for now)
- Bulk rating operations
- Exporting or sharing ratings
