---
title: "US-015: Game Detail View & Unmerge"
date: 2026-05-05
tags: [user-story, library, detail-view, unmerge, merge]
status: done
---

## As a...
A gamer managing my multi-platform library

## I want to...
- Click any game card to open a **detail view** showing all data held for that game across every platform it's owned on
- If the game was created by merging two entries, see which original entries were combined and be able to **unmerge** them back into separate cards

## So that...
- I can inspect the full picture for a game without scrolling through a list or hunting in multiple filter views
- I can safely recover from an accidental or incorrect merge without needing a full re-sync

---

## Acceptance Criteria

### Detail view
- [ ] Clicking anywhere on a game card (outside the action buttons) opens the detail view
- [ ] The detail view is a full-page route at `/library/games/{game_id}` — not a modal — so it is linkable and navigable with the browser back button
- [ ] The page displays:
  - Game title and cover art
  - All platforms the game is owned on, with per-platform data in tabs or sections:
    - **Steam**: total playtime, last played, first played, never launched flag, achievement %, genres, tags, Steam categories, my review
    - **PSN**: trophy progress %, trophies earned/defined, PS4/PS5 platform flag, acquisition type
    - **GOG**: release date
    - **Switch**: total playtime
  - Store availability badges (On Steam / On GOG) where applicable
  - User rating (thumbs up/down) and hidden state, with the ability to change them inline
  - Genre tags at the bottom

### Unmerge
- [ ] If the game has one or more entries merged into it (`games.merged_into = this game's id`), a clearly labelled **Merged entries** section appears on the detail page listing the original game titles
- [ ] Each merged entry shows its platform badges so the user can confirm which one it is
- [ ] An **Unmerge** button (per merged entry, or a single "Unmerge all" if there is only one) triggers a confirmation prompt: *"This will restore [title] as a separate card. The two entries will appear independently again in your library."*
- [ ] On confirmation, `POST /library/games/{game_id}/unmerge` sets `merged_into = NULL` on the target entry and returns the newly independent game id
- [ ] The detail page refreshes — if all merged entries have been separated, the Merged entries section disappears
- [ ] The unmerged game immediately reappears as its own card in the library grid

---

## Out of Scope
- Editing game metadata (title, cover) from the detail page
- Merging additional games from the detail page (that stays on the library grid)
- Per-platform playtime breakdown beyond what is already stored in `library.playtime_mins` and `stg_psn_library`
