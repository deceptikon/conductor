---
type: story
status: To Do
priority: P0
created: 2026-06-16
updated: 2026-06-16
id: STORY-94
epic: "[[EPIC-15]]"
title: Core Path Resolution (paths.py)
tags: [bootstrap, cicd, database, frontend, infra, infrastructure, observability, paths, pult, testing]
related: "[[EPIC-15]], [[STORY-95]]"
---

# STORY-94: Core Path Resolution (`paths.py`)

## Context

The CHECKPOINT_POSTMORTEM identified a path bug in three Python scripts caused
by incorrect `.parent` traversals and hardcoded paths. The root cause is that
every script resolves `REPO_ROOT`, `VAULT`, and `BOOTSTRAP` independently with
copy-pasted heuristics — there is no single authoritative source.

`session_bootstrap.sh` uses `${VAULT:-/home/lexx/Documents/ADLAI/adlai-vault}`
(hardcoded absolute path). Python callers duplicate similar guesses. When the
repo is cloned to a different location (e.g., `/home/lexx/Q/ADLAI`), all three
fail silently.

The postmortem fix: `assert BOOTSTRAP.exists()` at startup. Find repo root by
anchor file (`pyproject.toml`), not by guessing.

## Goal

Create `backend/app/services/paths.py` — a single, importable module that
resolves all critical paths at import time and asserts their existence.
Every other Python service and pult module imports from here. No other file
may hardcode repo or vault paths.

## Acceptance Criteria

- [ ] `backend/app/services/paths.py` exists
- [ ] `REPO_ROOT` is resolved by walking upward from `__file__` until `pyproject.toml` is found (raises `RuntimeError` if not found)
- [ ] `VAULT` = `REPO_ROOT / "adlai-vault"` (overridable via `VAULT` env var)
- [ ] `BOOTSTRAP` = `VAULT / "00_Project" / "session_bootstrap.sh"`
- [ ] `LOGS_DIR` = `VAULT / "00_Project" / "logs"`
- [ ] Module asserts `BOOTSTRAP.exists()` on import; raises `EnvironmentError` with clear message if not
- [ ] `LOGS_DIR` is created with `mkdir(parents=True, exist_ok=True)` on import
- [ ] Unit tests in `backend/tests/unit/test_paths.py` cover:
  - Path types are `pathlib.Path` instances
  - `REPO_ROOT` contains `pyproject.toml`
  - `BOOTSTRAP` is found and is a file
  - Env var `VAULT` override works correctly
- [ ] `uv run pytest backend/tests/unit/test_paths.py -q` exits 0
- [ ] `ruff check backend/app/services/paths.py` clean

## Implementation Notes

```python
# backend/app/services/paths.py
import os
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    """Walk upward until pyproject.toml is found."""
    for parent in [start, *start.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError(
        f"Cannot locate repo root: no pyproject.toml found above {start}"
    )

REPO_ROOT: Path = _find_repo_root(Path(__file__).resolve())
VAULT: Path = Path(os.environ.get("VAULT", str(REPO_ROOT / "adlai-vault")))
BOOTSTRAP: Path = VAULT / "00_Project" / "session_bootstrap.sh"
LOGS_DIR: Path = VAULT / "00_Project" / "logs"

# Fail loud at import time, not silently at runtime
if not BOOTSTRAP.exists():
    raise EnvironmentError(
        f"Bootstrap script not found at {BOOTSTRAP}. "
        f"Is VAULT env var set correctly? (current: {VAULT})"
    )

LOGS_DIR.mkdir(parents=True, exist_ok=True)
```

## Files to Touch

| File | Action |
|------|--------|
| `backend/app/services/paths.py` | **CREATE** |
| `backend/tests/unit/test_paths.py` | **CREATE** |

## Definition of Done

- `paths.py` exists with `REPO_ROOT`, `VAULT`, `BOOTSTRAP`, `LOGS_DIR`
- `assert BOOTSTRAP.exists()` equivalent fires loudly if path is wrong
- Unit tests pass
- `ruff` clean

## L3 Artifacts
<!-- reserved for phase artifacts written by the agent during execution -->
