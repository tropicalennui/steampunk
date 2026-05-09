# SteamPunk Workspace — Claude Code Conventions

## Runtime Safety

**Never edit any file while a sync is running.** The dev server runs with hot-reload (WatchFiles). Any file change — including `.py`, `.html`, `.sql`, or any other watched file — triggers an immediate server restart that kills the active sync process mid-run, corrupting or losing that run's data.

Before making any code or template change, confirm the sync has finished (log page shows completion, or the user confirms it). If unsure, ask.

## Security & Privacy

- **PII must never be committed.** Any file containing personal data must be gitignored. See `.gitignore` for patterns; add new patterns immediately if a new PII format is introduced.
- **Secrets must never appear in plain text in any committed file.** All secrets (API keys, tokens, credentials, connection strings) are stored in `gandalf.json` at the workspace root. That file is gitignored and must never be committed.
- When referencing a secret in code or docs, use a placeholder name (e.g. `OPENAI_API_KEY`) and note that the value lives in `gandalf.json`.

## Git Workflow

**Never commit directly to `main`.** All work happens on a branch.

### Branch naming
| Prefix | Use for |
|---|---|
| `feature/` | New user-facing functionality |
| `chore/` | Maintenance, refactoring, tooling, dependencies |
| `bug/` | Bug fixes |
| `docs/` | Documentation-only changes |

Use `kebab-case` after the prefix. Delete branches after merging.

### Commit messages
```
<type>(<scope>): <short summary>   ← imperative, lowercase, ≤72 chars
```
Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`. Add a body when the *why* isn't obvious. Never include secrets or PII in commit messages.

### Merging to main
1. Read SonarQube config from `gandalf.json` key `sonarqube` → `token`, `host`, `project_key`
2. Run the scanner (full path required — not on PATH):
   ```
   & "C:\Users\rjing\AppData\Roaming\Python\Python313\Scripts\pysonar.exe" `
     --sonar-host-url=<host> `
     --sonar-token=<token> `
     --sonar-project-key=<project_key>
   ```
3. Confirm zero open issues via the API:
   ```powershell
   $h = @{ Authorization = "Bearer <token>" }
   (Invoke-RestMethod "http://localhost:9000/api/issues/search?projectKeys=Steampunk&statuses=OPEN&ps=1" -Headers $h).total
   ```
   Must return `0`. If not, fix all issues on the branch and re-scan.
4. Push the branch to GitHub and open a PR targeting `main`.
5. Merge the PR on GitHub (squash or merge commit — your choice). Delete the branch after merging.

The SonarQube gate is the quality check before opening the PR.

### Release notes (release-please)
A GitHub Action ([`.github/workflows/release-please.yml`](.github/workflows/release-please.yml)) watches `main` for conventional commits and automatically opens a **Release PR** that bumps the version and updates `CHANGELOG.md`. Merging that PR creates a GitHub Release.

- `feat` commits → minor version bump, appear under **Features** in the changelog
- `fix` commits → patch bump, appear under **Bug Fixes**
- `refactor` commits → patch bump, appear under **Refactoring**
- `chore` / `docs` commits → patch bump, hidden from the public changelog
- `feat!` or `fix!` (breaking change) → major version bump

### Secrets in sonar-project.properties
`sonar-project.properties` is gitignored — never commit it. The SonarQube token lives in `gandalf.json` under key `sonarqube.token`.

## Feature Development Workflow

Every workspace feature must go through this sequence before implementation:

1. **User Story** — written first, saved in `SteamPunkVault/Stories/`
2. **High-Level Design (HLD)** — saved in `SteamPunkVault/High-Level-Designs/`
3. **User Guide** — saved in `SteamPunkVault/User-Guides/`

Do not begin implementation until both the User Story and HLD exist. Do not mark a feature complete until the User Guide exists.

## Documentation Standards

- All documentation is written in **Markdown** using **Obsidian conventions**:
  - Internal links use `[[Note Name]]` syntax
  - Tags use `#tag` inline or in frontmatter
  - Each document has YAML frontmatter with at minimum `title`, `date`, and `tags`
- All documentation lives under `SteamPunkVault/`
- File names use `Kebab-Case` (e.g. `My-Feature-HLD.md`)

## Vault Folder Map

| Folder | Purpose |
|---|---|
| `SteamPunkVault/Stories/` | User Stories (one file per feature) |
| `SteamPunkVault/High-Level-Designs/` | High-Level Design documents |
| `SteamPunkVault/User-Guides/` | End-user guides and how-tos |
| `SteamPunkVault/Ideas/` | Possible future features — investigated but not yet committed to a story |

## Document Templates

### User Story (`SteamPunkVault/Stories/`)
```markdown
---
title: "US-XXX: <Feature Name>"
date: YYYY-MM-DD
tags: [user-story, <feature-tag>]
status: draft | ready | in-progress | done
---

## As a...
## I want to...
## So that...

## Acceptance Criteria
- [ ] ...
```

### High-Level Design (`SteamPunkVault/High-Level-Designs/`)
```markdown
---
title: "HLD: <Feature Name>"
date: YYYY-MM-DD
tags: [hld, <feature-tag>]
story: "[[US-XXX: <Feature Name>]]"
status: draft | approved | implemented
---

## Overview
## Goals & Non-Goals
## Design
## Data & Privacy Considerations
## Open Questions
```

### User Guide (`SteamPunkVault/User-Guides/`)
```markdown
---
title: "Guide: <Feature Name>"
date: YYYY-MM-DD
tags: [user-guide, <feature-tag>]
story: "[[US-XXX: <Feature Name>]]"
---

## Overview
## Prerequisites
## Step-by-Step
## Troubleshooting
```
