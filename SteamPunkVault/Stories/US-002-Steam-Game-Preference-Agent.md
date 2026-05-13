---
title: "US-002: Steam Game Preference Agent"
date: 2026-05-01
tags: [user-story, steam, recommendations, agent]
depends-on: "[[US-001: Steam Auth & Library Viewer]]"
status: draft
---

## As a...
A logged-in user with a populated Steam library

## I want to...
Chat with an AI agent that knows my gaming history and can recommend games based on what I feel like playing — with optional filters like price range

## So that...
I can get personalised game recommendations that reflect my actual play patterns, not generic store suggestions

## Acceptance Criteria

### Chat Interface
- [ ] After login, the home page presents an agent chat interface
- [ ] Opening message from the agent: "What are you feeling like today?"
- [ ] Chat supports multi-turn conversation
- [ ] Agent responses stream in real time (not a single delayed block)

### Preference Profile
- [ ] Agent has access to a preference profile built from: playtime, tags/genres, wishlist, achievement completion rate, never-launched games, and written reviews
- [ ] Profile is persisted in `data/profile.json` per user account
- [ ] Profile is rebuilt when the data pipeline is refreshed

### Recommendations
- [ ] Agent can recommend games the user does not yet own
- [ ] Recommendations are ranked by fit with the preference profile
- [ ] Each recommendation includes a brief explanation of why it was suggested
- [ ] User can ask for recommendations filtered by price range (e.g. "under $20")
- [ ] Sexually explicit content excluded from recommendations by default
- [ ] Additional content/scope filters to be defined after initial data exploration

### Signals Used (beyond game catalog)
- [ ] Wishlist — positive intent signal
- [ ] Never-launched games — negative/neutral signal
- [ ] Achievement completion rate — depth-of-engagement signal
- [ ] User-written Steam reviews — direct sentiment signal

## Open Questions
- How should conflicting signals be weighted? (e.g. owned + never launched a genre, but wishlisted in the same genre)
- Should recommendation results be persisted or generated fresh each session?

## Out of Scope (for now)
- Friends / social data
- Real-time "what should I play tonight" mode
