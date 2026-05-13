---
title: "US-009: Preference Learning"
date: 2026-05-03
tags: [user-story, agent, preferences, quiz, ratings, recommendations]
depends-on: "[[US-002: Steam Game Preference Agent]]"
absorbs: "[[US-004: Game Ratings]]"
status: in-progress
---

## As a...
A user with a multi-platform game library, including platforms where play metrics are absent or unreliable

## I want to...
Rate games I've played, and have the agent actively quiz me on my preferences in an A-or-B format — so both my explicit ratings and my explained comparisons feed into a preference model

## So that...
The agent builds a picture of what I enjoy that goes beyond incomplete cross-platform play data, and can recommend games I'll actually want to play

## Acceptance Criteria

### Thumbs Ratings (from US-004 — rating implemented, filter outstanding)
- [x] User can rate any game thumbs up or thumbs down via a single click on the game card
- [x] Clicking the active rating again clears it (toggle behaviour)
- [x] Rating is stored per canonical game (`user_game_prefs.rating`)
- [x] Rating applies across platforms — rating a Steam copy also rates the linked GOG copy
- [x] Rating state is reflected immediately in the UI (optimistic update)
- [ ] Library can be filtered to show only liked games (thumbs up)
- [ ] Library can be filtered to show only disliked games (thumbs down)
- [ ] Rating filter combines with the existing platform filter and text search

### Quiz Flow
- [ ] User can trigger the quiz by asking the agent something like "let's do a preference quiz" or "rank my games"
- [ ] Agent presents two games (Game A or Game B) and asks which the user preferred
- [ ] Each prompt includes brief context — platform, playtime or trophy % if available
- [ ] User picks A or B and optionally explains why (free text)
- [ ] Agent acknowledges the choice, reflects back what it learned, and asks the next pair
- [ ] User can end the quiz at any time ("that's enough for now")
- [ ] Session minimum: 5 pairs before the agent considers the profile meaningfully updated

### Pair Selection
- [ ] Agent prioritises pairs where it has least signal — GOG-only games, PSN games with no trophy activity, never-launched Steam games
- [ ] Agent avoids pitting two games from the same series against each other
- [ ] Agent avoids pairs where one game is obviously dominant unless probing to confirm an outlier
- [ ] Over time, pairs shift toward cross-genre and cross-platform comparisons to build a richer model

### Learning & Persistence
- [ ] Quiz responses and thumbs ratings are both stored in `data/profile.json` as preference signals
- [ ] Each quiz entry records: game_a, game_b, chosen, reason (if given), timestamp
- [ ] Profile is not overwritten by a pipeline refresh — preference data is additive and permanent until explicitly cleared
- [ ] Agent weights quiz and rating signals at least as highly as playtime signals when making recommendations

### Agent Behaviour
- [ ] Agent explains its reasoning for recommendations that draw on preference data
- [ ] Agent can summarise the preference model on request ("What have you learned about my taste?")
- [ ] Agent can flag when a recommendation conflicts with stated preferences and explain the tradeoff

## Out of Scope (for now)
- Numeric or star ratings (thumbs up/down is sufficient)
- Bulk rating operations
- Importing preferences from external sources
- Multi-user profiles
- Automatic re-quiz prompts on a schedule

## Open Questions
- Should the quiz be a separate UI mode or purely conversational within the existing chat interface?
- How many quiz pairs before the model is considered "warm" enough to suppress the "I don't have enough data" caveat on recommendations?
