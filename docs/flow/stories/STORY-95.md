---
type: story
status: To Do
priority: P0
created: 2026-06-16
updated: 2026-06-16
id: STORY-95
epic: "[[EPIC-15]]"
title: Pult Phase 1 — Python Wrapper and Error Classifier
tags: [cicd, error-classifier, frontend, infra, llm, logging, observability, pult, routing, testing, workflow]
related: "[[EPIC-15]], [[STORY-94]], [[STORY-96]], [[STORY-97]], [[STORY-98]]"
depends_on: "[[STORY-94]]"
---

# STORY-95: Pult Phase 1 — Python Wrapper & Error Classifier

## Context

The postmortem identifies **Problem 4** ("No Pult") and **Problem 2** ("Silent
Diagnostic Failures") as root blockers for reliable automated execution.

Currently `session_bootstrap.sh` is a shell script that produces a prompt
string. There is no entry point to:
- Run a full `SYNC → ENGAGE → ACT → WRAP` lifecycle
- Capture and classify errors from stderr
- Log structured diagnostics to the vault
- Surface a clean failure message when `rvc`, `git`, or the bootstrap script
  is unavailable

`pult` fills this gap. Phase 1 focuses on the wrapper + error classifier: no
phase chaining yet (that is [[STORY-96]]), but all error surfaces are captured and
structured.

## Goal

Create `backend/app/services/pult.py` with:
1. `Pult` class — the canonical entry point that wraps `session_bootstrap.sh`
2. `ErrorClassifier` — classifies raw stderr lines into structured error records
3. Structured JSON logging to `adlai-vault/00_Project/logs/`
4. CLI entry point: `python -m backend.app.services.pult run STORY-XX --phase sync`

## Acceptance Criteria

- [ ] `backend/app/services/pult.py` exists
- [ ] `Pult.run(story_id, phase)` executes `session_bootstrap.sh --phase <phase> <story_id>` via `subprocess`
- [ ] stdout of bootstrap is captured and returned (not printed directly)
- [ ] stderr is captured and classified by `ErrorClassifier` into one of:
  - `MISSING_CLI` — command not found (rvc, git, etc.)
  - `INVALID_PATH` — file/directory not found
  - `GIT_FAILURE` — git command exited non-zero
  - `BOOTSTRAP_ERROR` — exit code non-zero from bootstrap script
  - `UNKNOWN` — anything else
- [ ] On any classified error, a JSON log is written to `LOGS_DIR/<timestamp>_pult_<story_id>_<phase>.json` with fields:
  - `story_id`, `phase`, `error_class`, `message`, `raw_stderr`, `timestamp` (ISO-8601), `exit_code`
- [ ] A `PultError` exception is raised with the structured payload when the script fails
- [ ] On success, `Pult.run()` returns the prompt string (stdout)
- [ ] `python -m backend.app.services.pult run STORY-XX --phase sync` prints the prompt to stdout
- [ ] Unit tests in `backend/tests/unit/test_pult.py` cover (all mocked, no real subprocess):
  - Successful run returns stdout string
  - stderr "rvc: command not found" → `MISSING_CLI` classification
  - stderr "No such file or directory" → `INVALID_PATH` classification
  - Non-zero exit code → `BOOTSTRAP_ERROR` + `PultError` raised
  - JSON log file is written on failure (use `tmp_path` fixture)
- [ ] `uv run pytest backend/tests/unit/test_pult.py -q` exits 0
- [ ] `ruff check backend/app/services/pult.py` clean
- [ ] Imports `REPO_ROOT`, `BOOTSTRAP`, `LOGS_DIR` exclusively from `paths.py` ([[STORY-94]])

## Implementation Sketch

```python
# backend/app/services/pult.py
import json, subprocess, sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import NamedTuple

from backend.app.services.paths import BOOTSTRAP, LOGS_DIR

class ErrorClass(str, Enum):
    MISSING_CLI    = "MISSING_CLI"
    INVALID_PATH   = "INVALID_PATH"
    GIT_FAILURE    = "GIT_FAILURE"
    BOOTSTRAP_ERROR = "BOOTSTRAP_ERROR"
    UNKNOWN        = "UNKNOWN"

class PultError(RuntimeError):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload["message"])

class ErrorClassifier:
    RULES = [
        (["command not found", "No command"], ErrorClass.MISSING_CLI),
        (["No such file or directory", "not found"], ErrorClass.INVALID_PATH),
        (["fatal:", "error: git"], ErrorClass.GIT_FAILURE),
    ]
    def classify(self, stderr: str, exit_code: int) -> ErrorClass:
        for patterns, cls in self.RULES:
            if any(p in stderr for p in patterns):
                return cls
        if exit_code != 0:
            return ErrorClass.BOOTSTRAP_ERROR
        return ErrorClass.UNKNOWN

class Pult:
    def __init__(self):
        self.classifier = ErrorClassifier()

    def run(self, story_id: str, phase: str) -> str:
        result = subprocess.run(
            ["bash", str(BOOTSTRAP), "--phase", phase, story_id],
            capture_output=True, text=True
        )
        if result.returncode != 0 or result.stderr.strip():
            ec = self.classifier.classify(result.stderr, result.returncode)
            payload = {
                "story_id": story_id, "phase": phase,
                "error_class": ec.value,
                "message": result.stderr.strip() or f"exit {result.returncode}",
                "raw_stderr": result.stderr,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "exit_code": result.returncode,
            }
            log_path = LOGS_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{story_id}_{phase}.json"
            log_path.write_text(json.dumps(payload, indent=2))
            if result.returncode != 0:
                raise PultError(payload)
        return result.stdout

if __name__ == "__main__":
    # CLI: python -m backend.app.services.pult run STORY-XX --phase sync
    import argparse
    parser = argparse.ArgumentParser(prog="pult")
    sub = parser.add_subparsers(dest="cmd")
    run_p = sub.add_parser("run")
    run_p.add_argument("story_id")
    run_p.add_argument("--phase", required=True)
    args = parser.parse_args()
    if args.cmd == "run":
        print(Pult().run(args.story_id, args.phase))
```

## Files to Touch

| File | Action |
|------|--------|
| `backend/app/services/pult.py` | **CREATE** |
| `backend/tests/unit/test_pult.py` | **CREATE** |

## Definition of Done

- `pult.py` exists with `Pult`, `ErrorClassifier`, `PultError`
- CLI `python -m backend.app.services.pult run STORY-XX --phase sync` works
- All stderr errors produce a classified JSON log in vault
- Unit tests pass with mocked subprocess
- `ruff` clean

## L3 Artifacts
<!-- reserved for phase artifacts written by the agent during execution -->
