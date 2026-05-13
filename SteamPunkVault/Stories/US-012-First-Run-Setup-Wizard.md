---
title: "US-012: First-Run Setup Wizard"
date: 2026-05-03
tags: [user-story, onboarding, setup, packaging, distribution]
status: draft
---

## As a...
A new user who has just installed SteamPunk for the first time

## I want to...
Be guided through linking my game libraries entirely within the app, without ever manually editing a config file or visiting a developer portal

## So that...
I can go from a fresh install to a populated library by following clear in-app instructions

## Acceptance Criteria

### First-Run Detection
- [ ] App detects on launch that no services are configured and enters setup wizard mode automatically
- [ ] Wizard can also be re-triggered manually from Connected Services settings

### Steam Setup
- [ ] App explains what a Steam API key is and provides a direct link to the Steam API key registration page
- [ ] User pastes their API key and Steam vanity URL/ID into the app — no manual file editing
- [ ] App validates the key before proceeding

### Other Services
- [ ] Wizard presents all supported services (GOG, PSN, Nintendo Switch) with the option to skip any
- [ ] Each service's setup flow is the in-app flow defined in its respective story (OAuth, NPSSO paste, Nintendo redirect URL paste)
- [ ] At least one service must be connected before the wizard completes

### Credential Storage
- [ ] All user-provided credentials are written to `gandalf.json` by the app — users never touch that file directly
- [ ] Bundled credentials (IGDB, GOG client ID/secret) are compiled into the exe and never surfaced to the user

### Completion
- [ ] On completing the wizard, app triggers an initial sync and takes the user to the library view

## Out of Scope (for now)
- Wizard progress saved across app restarts (restart = start wizard again)
- Account switching or multi-user setup

## Open Questions
- Should Steam API key setup remain manual (user gets key from Steam website) or can it be further automated?
