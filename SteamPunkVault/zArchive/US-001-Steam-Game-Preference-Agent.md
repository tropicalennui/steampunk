---
title: "US-001: Steam Game Preference Agent"
date: 2026-05-01
tags: [user-story, steam, recommendations, agent]
status: superseded
---

## As a...
A Steam user who has played a lot of games

## I want to...
Have an AI agent that knows my gaming history — what I own, how long I've played each game, and what tags/genres they belong to — and uses that knowledge to recommend games I'm likely to enjoy

## So that...
I can discover new games that match my actual play patterns rather than relying on generic store recommendations

## Acceptance Criteria

### Core Library Data
- [ ] Agent retrieves the full list of games I own on Steam via the API
- [ ] Agent captures playtime data (total hours) per game
- [ ] Agent enriches each game with tag and genre metadata from the Steam Store API

### Preference Signals (beyond the catalog)
- [ ] Agent reads my Steam wishlist as a positive intent signal (things I want but haven't bought)
- [ ] Agent identifies games I own but have never launched as negative/neutral signals
- [ ] Agent uses achievement completion rate per game as a depth-of-engagement signal
- [ ] Agent reads any Steam reviews I have written for direct sentiment data
- [ ] Parameters around content filtering to be defined after initial data exploration (explicit content excluded by default)

### Recommendations
- [ ] Agent builds a preference profile from all available signals, persisted per user account
- [ ] Agent recommends games I don't yet own, ranked by fit with my preference profile
- [ ] Recommendations include a brief explanation of why each game was suggested
- [ ] User can optionally specify a price range to filter recommendations
- [ ] Recommendation scope and content filters (e.g. rating thresholds) to be defined post data exploration

## Open Questions
- What other Steam data signals are accessible via the public API? (e.g. session length history)
- How should conflicting signals be weighted? (e.g. owned + never launched a genre, but wishlisted another in the same genre)

## Out of Scope (for now)
- Friends / social data
- Real-time "what should I play tonight" mode

## Superseded By
[[US-001: Steam Auth & Library Viewer]], [[US-002: Steam Game Preference Agent]]
