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

# STORY-96: Pult Phase 2 — Structured Artifact Injection

## Context

**Problem 5** from the postmortem: only the SYNC phase has automated artifact
injection. ENGAGE, ACT, and WRAP artifacts are written by the LLM manually
from a markdown description. This leads to:
- Format drift (agent omits required fields)
- Failed gate validation (next phase cannot parse the artifact)
- Silent failures (gate reads artifact, finds no `status=ready`, blocks)

The L3 spec defines the artifact format for all 4 phases. Currently only
`session_bootstrap.sh` writes SYNC artifacts. ENGAGE/ACT/WRAP have no
template injection mechanism.

## Goal

Extend `pult.py` with `ArtifactInjector` — a class that, after a successful
phase run, injects a **blank template** artifact into the story file for the
LLM to fill in. This ensures the structure is always present and parseable
by the next phase's gate, even if the LLM only needs to fill in values.

Additionally, extend `Pult.run()` to accept a `--inject-template` flag that
writes the blank template immediately after the prompt is generated.

## Acceptance Criteria

- [ ] `ArtifactInjector` class exists in `pult.py`
- [ ] `ArtifactInjector.inject(story_id, phase, story_file_path)` inserts a blank template block into the story `.md` file in the correct format:
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
- [ ] `Pult.run()` accepts optional `inject_template: bool = False` parameter; when True, calls `ArtifactInjector.inject()` after generating the prompt
- [ ] CLI flag `--inject-template` maps to `inject_template=True`
- [ ] **Implement artifact publishing to FLOW vault with cross-vault link resolution** (matching dream flow `pult_node` behaviour): after WRAP phase, publish final artifacts to `FLOW/artifacts/` with resolved cross-vault wikilinks
- [ ] **G3 gate:** verify predecessor phase artifact exists with `status=ready` before injecting next phase template; fail with `GATE_FAIL` classification + structured log if not
- [ ] **G2 gate:** validate injected artifact template has all required fields before writing to story file; fail with `BOOTSTRAP_ERROR` if template is malformed
- [ ] Unit tests in `backend/tests/unit/test_artifact_injector.py` cover:
  - SYNC template injection into a fresh story file
  - ENGAGE template injection
  - ACT template injection
  - WRAP template injection
  - Idempotency: second injection does not duplicate the block
  - Missing `## L3 Artifacts` section is created automatically
  - Existing `status=ready` block is NOT overwritten
  - **G3 gate: injection blocked when predecessor artifact is missing/pending**
  - **G2 gate: malformed template rejected before write**
- [ ] `uv run pytest backend/tests/unit/test_artifact_injector.py -q` exits 0
- [ ] `ruff check backend/app/services/pult.py` clean (after edits)

## Edge Cases & Error Scenarios

| Scenario | Expected Behaviour |
|----------|-------------------|
| Story file is read-only | `BOOTSTRAP_ERROR` with "permission denied" before attempting write |
| `## L3 Artifacts` section exists but has malformed prior blocks | Append new block after last valid block; do not attempt to repair malformed blocks |
| Template injection called for `phase=sync` on a story that already has `status=ready` SYNC artifact | Idempotent: no new block injected (existing ready block preserved) |
| Cross-vault link in artifact points to non-existent vault | Log warning, write artifact with unresolved link, do not fail |
| FLOW vault directory does not exist | Auto-create on first publish; fail with `INVALID_PATH` if unresolvable via `paths.py` |

## Non-Functional Requirements

- **Performance:** Injection must complete in <100ms per phase
- **Concurrency:** Safe for concurrent injection on different story files (file-level locking not required, story-level isolation assumed)
- **Observability:** Every injection attempt produces a log entry (success, idempotent skip, or failure)

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
