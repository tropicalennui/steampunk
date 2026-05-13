---
title: "US-005: Game Tags"
date: 2026-05-03
tags: [user-story, steam, library, tags]
status: draft
---

## As a...
A Steam user browsing my game library

## I want to...
See the Steam tags associated with each game and filter my library by tag

## So that...
I can quickly find games by mood, genre, or play style without having to remember exact genre names

## Acceptance Criteria

### Games List page
- [ ] Each game card displays its Steam user tags alongside genres
- [ ] The search / filter bar supports filtering by tag
- [ ] Tag filter and genre filter can be combined (AND logic)

### Data pipeline
- [ ] `collect.py` fetches Steam tags for each owned game and stores them in the `game_tags` table
- [ ] Tags are included in the library query result passed to the template

## Out of Scope (for now)
- Tag management or editing (Steam tags are read-only)
- Tag-based recommendations (covered in [[US-002: Steam Game Preference Agent]])
