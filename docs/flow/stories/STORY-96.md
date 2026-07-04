---
aliases:
  - STORY-96
type: story
status: To Do
priority: P1
created: 2026-06-16
updated: 2026-06-16
id: STORY-96
epic: "[[EPIC-15]]"
title: Pult Phase 2 — Structured Artifact Injection
tags: [phase-gating, pult, workflow]
related: "[[EPIC-15]], [[STORY-95]], [[STORY-99]], [[L3_PHASE_GATING]]"
depends_on: "[[STORY-95]]"
domain: workflow_meta
domain_tags: ["story", "testing"]
---

# STORY-96: Pult Phase 2 — Structured Artifact Injection & Publishing

## Context

**Problem 5** from the postmortem: only the SYNC phase has automated artifact
injection. ENGAGE, ACT, and WRAP artifacts are written by the LLM manually
from a markdown description. This leads to:
- Format drift (agent omits required fields)
- Failed gate validation (next phase cannot parse the artifact)
- Silent failures (gate reads artifact, finds no `status=ready`, blocks)

Additionally, the dream flow shows `pult_node` publishing artifacts to the FLOW
vault after commit — this is currently missing entirely.

The L3 spec defines the artifact format for all 4 phases. Currently only
`session_bootstrap.sh` writes SYNC artifacts. ENGAGE/ACT/WRAP have no
template injection mechanism, and no publishing mechanism exists.

## Goal

Extend `pult.py` with two new subcommands:

1. `pult inject <story_id> --phase <phase>` — inject a **blank template** artifact
   into the story file for the LLM to fill in. Ensures structure is always present
   and parseable by the next phase's gate.

2. `pult publish <story_id>` — publish final artifacts to the FLOW vault after
   WRAP phase completes, with cross-vault link resolution (matching dream flow
   `pult_node` behaviour).

These replace the artifact injection logic that was buried inside
`session_bootstrap.sh:144-192` (SYNC auto-gen) and add the missing publishing
step.

## Acceptance Criteria

### `pult inject` subcommand

- [ ] `pult inject <story_id> --phase <phase>` inserts a blank template block into the story `.md` file in the correct format:
  ```html
  <!-- l3:phase=<phase> story=<story_id> status=pending version=1 -->
  <template fields here>
  <!-- /l3:phase=<phase> -->
  ```
- [ ] Templates are defined for all 4 phases:
  - **SYNC**: `findings:`, `blockers:`, `git_head:`
  - **ENGAGE**: `plan_summary:`, `files_to_touch:`, `risks:`
  - **ACT**: `test_exit_code:`, `files_changed:`, `notes:`
  - **WRAP**: `commit_sha:`, `rvc_transition:`, `decisions_logged:`, `gotchas_logged:`
- [ ] Injection is **idempotent**: if a block already exists for this phase, it is not duplicated
- [ ] Injection locates the `## L3 Artifacts` section in the story file and appends below it (creating the section if missing)
- [ ] **G3 gate:** verify predecessor phase artifact exists with `status=ready` before injecting next phase template; fail with `GATE_FAIL` classification + structured log if not
- [ ] **G2 gate:** validate injected artifact template has all required fields before writing to story file; fail with `BOOTSTRAP_ERROR` if template is malformed

### `pult publish` subcommand

- [ ] `pult publish <story_id>` publishes final artifacts to FLOW vault:
  - Copies story file to `FLOW/artifacts/<story_id>/`
  - Resolves cross-vault wikilinks to canonical paths
  - Generates `manifest.json` with artifact metadata (timestamps, phases, status)
- [ ] Publishing is idempotent: re-running does not duplicate artifacts
- [ ] **G6 gate:** verify all spec references in published artifacts resolve to canonical copies in `TEAMFLOW/20_Specs/`

### Tests

- [ ] Unit tests in `backend/tests/unit/test_pult_inject.py` cover:
  - SYNC template injection into a fresh story file
  - ENGAGE/ACT/WRAP template injection
  - Idempotency: second injection does not duplicate
  - Missing `## L3 Artifacts` section created automatically
  - Existing `status=ready` block is NOT overwritten
  - G3 gate: injection blocked when predecessor artifact is missing/pending
  - G2 gate: malformed template rejected before write
- [ ] Unit tests in `backend/tests/unit/test_pult_publish.py` cover:
  - Publishing creates FLOW vault directory structure
  - Cross-vault links resolved correctly
  - Manifest.json generated with correct metadata
  - G6 gate: duplicate spec detection → warning logged
- [ ] `uv run pytest backend/tests/unit/test_pult_inject.py -q` exits 0
- [ ] `uv run pytest backend/tests/unit/test_pult_publish.py -q` exits 0
- [ ] `ruff check backend/app/services/pult.py` clean (after edits)

## Edge Cases & Error Scenarios

| Scenario | Expected Behaviour |
|----------|-------------------|
| Story file is read-only | `BOOTSTRAP_ERROR` with "permission denied" before attempting write |
| `## L3 Artifacts` section exists but has malformed prior blocks | Append new block after last valid block; do not attempt to repair malformed blocks |
| Template injection called for `phase=sync` on a story that already has `status=ready` SYNC artifact | Idempotent: no new block injected (existing ready block preserved) |
| Cross-vault link in artifact points to non-existent vault | Log warning, write artifact with unresolved link, do not fail |
| FLOW vault directory does not exist | Auto-create on first publish; fail with `INVALID_PATH` if unresolvable via `paths.py` |
| `pult publish` called before WRAP artifact is ready | G3 gate: fail with `GATE_FAIL`, do not publish incomplete artifacts |
| `pult inject` called without prior `pult validate` | Works independently (inject does not depend on validate), but logs warning |

## Non-Functional Requirements

- **Performance:** Injection must complete in <100ms per phase; publishing in <500ms
- **Concurrency:** Safe for concurrent injection on different story files (file-level locking not required, story-level isolation assumed)
- **Observability:** Every injection and publish attempt produces a log entry (success, idempotent skip, or failure)
- **Backward compatibility:** `session_bootstrap.sh` SYNC auto-generation continues to work while `pult inject` is being built

## Template Definitions

```python
PHASE_TEMPLATES = {
    "sync": """\
findings: |
  (agent fills in: what the issue requires, relevant specs found)
blockers: none
git_head: {git_head}
""",
    "engage": """\
plan_summary: |
  (agent fills in: numbered implementation plan)
files_to_touch:
  - (list files)
risks: none
""",
    "act": """\
test_exit_code: (agent fills in: 0 or non-zero)
files_changed:
  - (list changed files)
notes: |
  (agent fills in: what was done, deviations from plan)
""",
    "wrap": """\
commit_sha: (agent fills in: 7-char SHA after commit)
rvc_transition: (agent fills in: "rvc issue STORY-XX review" output)
decisions_logged: false
gotchas_logged: false
""",
}
```

## Files to Touch

| File | Action |
|------|--------|
| `backend/app/services/pult.py` | **EDIT** — add `ArtifactInjector`, extend `Pult.run()` |
| `backend/tests/unit/test_artifact_injector.py` | **CREATE** |

## Definition of Done

- `ArtifactInjector` with all 4 phase templates
- Idempotent injection: safe to call multiple times
- Unit tests pass
- CLI `--inject-template` flag works
- `ruff` clean

## L3 Artifacts
<!-- reserved for phase artifacts written by the agent during execution -->
