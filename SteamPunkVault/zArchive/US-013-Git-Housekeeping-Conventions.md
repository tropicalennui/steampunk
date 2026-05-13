---
title: "US-013: Git Housekeeping Conventions"
date: 2026-05-04
tags: [user-story, git, conventions, dx]
status: done
---

## As a...
Developer working on the SteamPunk project

## I want to...
Have a clearly defined git workflow — covering branching strategy, commit conventions, and PR requirements — so that changes are always reviewable, main is always stable, and the project history is clean and navigable.

## So that...
- No code lands on `main` without MY review
- All code is scanned by Sonarqube and all issues are resolve before code landing on main
- Each unit of work is traceable from branch → commit → PR
- The git log tells a clear story of what changed and why
- Accidental direct commits to `main` are blocked, not just discouraged

## Acceptance Criteria
- [x] Branch types and naming convention defined: `feature/`, `chore/`, `docs/`, `bug/`
- [x] Merge strategy defined: merge commits (no squash, no rebase)
- [x] Commit message format defined (structure, tense, length limits)
- [x] SonarQube scan required on every branch before merge to `main`; all issues must be resolved
- [x] No PRs required (solo developer); self-review via SonarQube gate is sufficient
- [x] `main` branch protection rules documented (no direct commits; push to remote only after merge)
- [x] Convention defined for hotfixes vs feature work
- [x] Conventions added to CLAUDE.md so Claude Code follows them automatically
- [x] Existing uncommitted changes bundled into appropriately named branches and merged via the new process
- [x] Secrets and tokens are never committed, even as comments — `sonar-project.properties` is gitignored and tokens live in `gandalf.json`
