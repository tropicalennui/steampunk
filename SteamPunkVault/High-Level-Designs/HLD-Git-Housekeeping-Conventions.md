---
title: "HLD: Git Housekeeping Conventions"
date: 2026-05-04
tags: [hld, git, conventions, dx]
story: "[[US-013: Git Housekeeping Conventions]]"
status: draft
---

## Overview

Defines the branching strategy, commit message format, and merge process for the SteamPunk project. The primary goals are a stable `main` branch, a clean readable history, and a mandatory SonarQube quality gate before any merge.

## Goals & Non-Goals

**Goals**
- Prevent direct commits to `main`
- Ensure every change is scanned by SonarQube (zero open issues before merge)
- Produce a git log that clearly communicates what changed and why
- Give Claude Code enough convention to follow the process autonomously

**Non-Goals**
- Pull request review process (solo project — not needed)
- CI/CD pipeline automation (manual scan is sufficient for now)
- Multi-contributor workflows (e.g. code owners, required reviewers)

## Design

### Branch Types and Naming

| Prefix | Purpose | Example |
|---|---|---|
| `feature/` | New user-facing functionality | `feature/psn-integration` |
| `chore/` | Maintenance, refactoring, tooling, dependency updates | `chore/sonarqube-cleanup` |
| `bug/` | Bug fixes | `bug/sync-crash-on-empty-library` |
| `docs/` | Documentation-only changes | `docs/setup-wizard-user-guide` |

- Use `kebab-case` after the prefix
- Keep names short but descriptive — enough to understand scope from `git branch`
- Delete branches after merging

### Workflow

```
1. Create branch from main
       git checkout -b chore/my-work

2. Do the work; commit regularly (see Commit Messages below)

3. Run SonarQube scan on the branch
       pysonar --sonar-host-url=http://localhost:9000 \
               --sonar-token=<token> \
               --sonar-project-key=Steampunk

4. Fix ALL open issues reported (Blocker → High → Medium → Low)
   Repeat scan until zero open issues remain.

5. Merge to main with a merge commit
       git checkout main
       git merge --no-ff <branch-name>

6. Push to remote
       git push origin main

7. Delete the branch
       git branch -d <branch-name>
```

**No direct commits to `main`.** If a change is small enough to feel like it doesn't need a branch, it still needs one — the SonarQube gate is the reason.

### Commit Messages

Structure (based on Conventional Commits, simplified):
```
<type>(<scope>): <short summary>

[optional body — wrap at 72 chars]
```

- **type**: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`
- **scope**: optional; the module or area affected (e.g. `psn`, `sync`, `ui`)
- **summary**: imperative mood, lowercase, no trailing period, ≤ 72 chars
- **body**: use when the *why* isn't obvious from the summary

Examples:
```
chore(sonarqube): resolve all blocker and high severity issues
feat(switch): add Nintendo Switch library sync
fix(psn): handle expired NPSSO token gracefully
docs: add setup wizard user guide
```

### Merge Strategy

Merge commits (`git merge --no-ff`). This preserves the branch topology in the log so it's always clear what was a discrete unit of work vs individual commits.

### Hotfixes

A hotfix is just a `bug/` branch — no special process. Branch from `main`, fix, scan, merge. The urgency doesn't bypass the SonarQube gate; a hotfix that introduces new issues is not ready to merge.

### SonarQube Gate

Before any merge to `main`:
1. Run `pysonar` against the branch
2. Query the API: `GET /api/issues/search?projectKeys=Steampunk&statuses=OPEN`
3. `total` must be `0`

If issues remain, fix them on the branch and re-scan. Do not merge until the gate passes.

### Branch Protection (GitHub)

Once a GitHub remote exists, apply these settings on `main`:
- Require a pull request before merging: **off** (solo dev)
- Require status checks: configure SonarQube scan as a required check if CI is added later
- Do not allow direct pushes: **on**

Until then, the convention is enforced by discipline and CLAUDE.md instructions.

## Data & Privacy Considerations

**`sonar-project.properties` is gitignored** and must never be committed. It may contain a `sonar.token` value which is a secret. The token lives in `gandalf.json`; `sonar-project.properties` should reference it only as a comment placeholder, never the actual value.

Commit messages must never contain secrets, tokens, or PII — even in "before/after" descriptions of changes.

## Open Questions

- When should branches be pushed to remote during development — continuously (for backup), or only at merge time?
