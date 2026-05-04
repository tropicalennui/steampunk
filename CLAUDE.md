# SteamPunk Workspace — Claude Code Conventions

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
4. Only then: `git checkout main && git merge --no-ff <branch>` then `git push origin main`
5. Delete the branch

No PRs required (solo project). The SonarQube gate is the quality check.

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
