---
title: "US-027: Sync Dropdown — Hierarchy and Per-Option Toggles"
date: 2026-05-09
tags: [user-story, sync, ui]
status: draft
---

## As a...
A user who syncs selectively across multiple platforms

## I want to...
A "Sync Now" dropdown that is genuinely two-level (platform groups with collapsible sub-items) and lets me toggle individual sync options on or off, so that clicking "Sync Now" only runs the options I have enabled

## So that...
The dropdown stays readable as more platforms and sub-steps are added, and I can configure a default sync scope without having to pick from the dropdown every time

---

## Background

The current dropdown has 8 items in a flat list. The Steam sub-items (`Library`, `Achievements`, `Wishlist`) are only visually indented — they are sibling `<button>` elements with no real hierarchy. "Sync Now" always submits `platforms=all` with no per-option control.

Clicking any dropdown item currently triggers an immediate sync for that platform — the dropdown acts as both a configuration surface and a trigger. The new design separates these concerns: the dropdown is configuration only, and "Sync Now" is always the trigger.

As more platforms and pipeline steps are added, the flat list will become hard to scan and too tall to use comfortably.

### Current dropdown items

| Label | Platform value |
|---|---|
| Steam | `steam` |
| Steam › Library | `steam:library` |
| Steam › Achievements | `steam:achievements` |
| Steam › Wishlist | `steam:wishlist` |
| GOG | `gog` |
| PlayStation | `psn` |
| Xbox | `xbox` |
| IGDB / Twitch | `igdb` |

---

## Acceptance Criteria

### Hierarchy
- [ ] Platform groups (Steam, GOG, PlayStation, Xbox, IGDB / Twitch) are top-level rows in the dropdown
- [ ] Groups that have sub-items (currently only Steam) are collapsible — clicking the group header expands or collapses the sub-items
- [ ] Groups with no sub-items behave as a single-action row (no expand/collapse chrome)
- [ ] Collapsed state is the default; last expanded state does not need to persist across page loads

### Per-option toggles
- [ ] Toggles are configuration only — interacting with a toggle never triggers a sync
- [ ] "Sync Now" is the sole sync trigger; it runs only the platforms/sub-items that are currently toggled on
- [ ] Each top-level platform group has a toggle that controls whether it is included in a "Sync Now" run
- [ ] Each sub-item within an expanded group has its own toggle
- [ ] When a platform group toggle is turned off, its sub-items are hidden from the dropdown entirely (not just dimmed)
- [ ] When a platform group toggle is turned on, its sub-items become visible again in their previous individual toggle states
- [ ] When all sub-items of a group are toggled off individually, the group-level toggle reflects the off state
- [ ] Toggle state persists in `localStorage` so the user's sync scope survives a page refresh
- [ ] "Sync Now" submits only the enabled platforms/sub-items as the `platforms` form value (comma-separated); if everything is toggled on it submits `all` as before

### UX
- [ ] The dropdown is wide enough to accommodate toggles without wrapping (wider than current `w-44`)
- [ ] Disabling all platforms shows a warning or disables the "Sync Now" button to prevent a no-op submit
- [ ] The logs page (`logs.html`) receives the same dropdown updates as `library.html`

### Out of scope
- Server-side persistence of toggle state (localStorage only for now)
- Adding new platforms or sub-items (that is separate feature work)
- Changing what each sync option actually does
