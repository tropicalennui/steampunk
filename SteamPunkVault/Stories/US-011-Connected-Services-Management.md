---
title: "US-011: Connected Services Management"
date: 2026-05-03
tags: [user-story, settings, preferences, services, onboarding, setup]
status: draft
---

## As a...
A user who does not own accounts on every supported gaming platform

## I want to...
See a clear list of all platforms SteamPunk supports, toggle on only the ones I actually use, and be taken directly to the setup flow for any platform I enable

## So that...
I am not confronted with setup prompts or UI surfaces for services I don't have, and linking a new platform is a single fluid action rather than navigating menus separately

## Acceptance Criteria

### Connected Services List
- [ ] A "Connected Services" section exists in user settings / preferences
- [ ] Every supported platform appears as a card or row (Steam, GOG, PlayStation Network, Nintendo Switch, and any future platforms)
- [ ] Each entry shows the platform name, icon, and one of three states: **Enabled & Connected**, **Enabled – Setup Required**, or **Disabled**
- [ ] Platforms default to **Disabled** for new installs; existing linked platforms default to **Enabled & Connected**

### Enabling a Service
- [ ] Toggling a platform from Disabled → Enabled immediately launches (or deep-links to) that platform's setup flow
- [ ] Completing setup transitions the platform to **Enabled & Connected**
- [ ] Abandoning setup mid-flow leaves the platform as **Enabled – Setup Required** (not Disabled), so the user can return

### Disabling a Service
- [ ] Toggling a platform from Enabled → Disabled stops it from being included in future pipeline syncs
- [ ] Disabling does not delete existing platform data — it only pauses collection
- [ ] A confirmation prompt is shown before disabling, noting that sync will be paused (not data deleted)
- [ ] Disabled platforms do not appear in the library platform filter or preference agent context

### Setup Navigation
- [ ] From the **Enabled – Setup Required** state, a "Set up" CTA navigates directly to that platform's setup flow
- [ ] From the **Enabled & Connected** state, a "Reconnect" CTA is available to re-run the auth flow (e.g. after token expiry)
- [ ] Setup flows for all platforms are reachable from this single screen — no platform has setup buried in a separate settings area

### Pipeline Behaviour
- [ ] `collect.py` reads enabled services from user preferences before syncing — only enabled platforms are synced per run
- [ ] A platform that is Enabled but missing credentials is skipped with a warning (not a hard failure)

### UI
- [ ] Disabled platforms are visually subdued but still legible (not hidden)
- [ ] State changes (toggle on/off, setup complete) are reflected immediately without a page reload

## Out of Scope (for now)
- Per-platform sync scheduling or frequency controls
- Multiple accounts per platform
- OAuth flows that require a browser redirect outside the app (each platform's auth UX is defined in its own story)

## Open Questions
- Should "Disabled" truly hide a platform from the library UI, or just exclude it from sync? Hiding feels cleanest but could confuse users who disable a service and then wonder where their games went.
	- Well, it's more to govern what the user wants to sign into, so obvs if they opt not to sign into it, we're not collecting any data about. If the user has already connected the service and chooses to disable it, they should be prompted as to whether they want any data they've collected about the service retained or not. if they don't want it retained, scrub anything in the data to do with that particular service (but, if for example they have the same game across multiple services, don't scrub any data that's still relevant to the other collected services)
- Where does this settings screen live — a dedicated `/settings/services` route, or a panel within the existing settings page?
	- In the drop down under the user icon, in Preferences, with an appropriate experience to break it up from other preferences

