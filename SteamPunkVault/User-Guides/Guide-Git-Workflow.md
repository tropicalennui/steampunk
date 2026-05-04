---
title: "Guide: Git Workflow"
date: 2026-05-04
tags: [user-guide, git, conventions, dx]
story: "[[US-013: Git Housekeeping Conventions]]"
---

## Overview

All work on SteamPunk follows a branch → scan → merge workflow. `main` is always stable and always clean in SonarQube. Nothing lands there without passing the quality gate.

## Prerequisites

- `pysonar` installed: `pip install pysonar`
- SonarQube running locally at `http://localhost:9000`
- `gandalf.json` contains a `sonarqube` key with `token`, `host`, and `project_key`

## Step-by-Step

### 1. Start a branch

Pick the right prefix for your work:

| Prefix | Use for |
|---|---|
| `feature/` | New user-facing functionality |
| `chore/` | Maintenance, refactoring, tooling, dependencies |
| `bug/` | Bug fixes |
| `docs/` | Documentation-only changes |

```powershell
git checkout -b chore/my-work
```

### 2. Do the work and commit

Commit message format:
```
<type>(<scope>): <short summary>
```
- Imperative mood, lowercase, ≤ 72 chars
- Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`
- Add a body paragraph when the *why* isn't obvious from the summary
- Never include secrets or PII in commit messages

```powershell
git add src/some_file.py
git commit -m "chore(sync): extract per-platform helpers to reduce complexity"
```

### 3. Run the SonarQube scan

Read the config from `gandalf.json` and run the scanner:

```powershell
$d = Get-Content gandalf.json | ConvertFrom-Json
& "C:\Users\rjing\AppData\Roaming\Python\Python313\Scripts\pysonar.exe" `
  --sonar-host-url=$($d.sonarqube.host) `
  --sonar-token=$($d.sonarqube.token) `
  --sonar-project-key=$($d.sonarqube.project_key)
```

### 4. Verify the gate

Wait a few seconds for the server to process, then check for zero open issues:

```powershell
$h = @{ Authorization = "Bearer $($d.sonarqube.token)" }
(Invoke-RestMethod "$($d.sonarqube.host)/api/issues/search?projectKeys=$($d.sonarqube.project_key)&statuses=OPEN&ps=1" -Headers $h).total
```

Must return `0`. If not, fix all issues on the branch (Blocker → High → Medium → Low → Info) and repeat from step 3.

### 5. Merge to main

```powershell
git checkout main
git merge --no-ff <branch-name>
git push origin main
git branch -d <branch-name>
```

## Troubleshooting

**`pysonar` is not recognised**
The executable is not on PATH. Use the full path: `C:\Users\rjing\AppData\Roaming\Python\Python313\Scripts\pysonar.exe`

**SonarQube token error / 401**
The token in `gandalf.json` may have expired. Generate a new one in SonarQube under Account → Security, update `gandalf.json`, and re-run.

**SonarQube not reachable**
Ensure the SonarQube server is running. Start it from the SonarQube `bin/` directory if needed.

**Issues still showing after a fix**
Re-run the scanner after making changes — SonarQube only updates when a new scan is submitted. Allow ~10 seconds for the server to process the report before querying the API.
