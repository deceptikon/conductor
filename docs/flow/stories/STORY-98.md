---
aliases:
  - STORY-98
type: story
status: To Do
priority: P1
created: 2026-06-16
updated: 2026-06-16
id: STORY-98
epic: "[[EPIC-15]]"
title: Real-Vault Integration Testing (Flow Tests)
tags: [workflow]
related: "[[EPIC-15]], [[STORY-95]], [[STORY-97]], [[STORY-99]]"
depends_on: "[[STORY-95]], [[STORY-97]]"
domain: workflow_meta
domain_tags: ["story", "testing"]
---

# STORY-98: Real-Vault Integration Testing (Flow Tests)

## Context

**Problem 3** from the postmortem: 103 unit tests run against `temp_vault`
fixtures with mocked paths and synthetic story files. They do not validate:
- Real vault layout (`adlai-vault/10_Issues/01_To_Do/*.md`)
- Real `rvc` CLI execution (mocked in unit tests)
- Real git state (branch, HEAD, dirty files)
- Real artifact file paths resolved by `paths.py`

The postmortem fix: at least 2 E2E integration tests that run against a real
`adlai-vault` snapshot (read-only clone), asserting the full
`SYNC → ENGAGE → ACT → WRAP` lifecycle for a fixture story.

These tests gate [[STORY-99]] (Pult Phase 3: Absorption) — we cannot deprecate
the bash bootstrap until the Python replacement passes E2E against the real
vault structure.

## Goal

Create `backend/tests/integration/test_flow_real_vault.py` with at minimum
2 E2E flow tests that:
1. Use the actual `adlai-vault/` directory (via `VAULT` env var override or
   real path from `paths.py`)
2. Call `Pult.run(story_id, phase)` (not mocked)
3. Assert real artifact files and prompt content against real story files

A **fixture story** (`STORY-TEST-FLOW`) will be created in the vault under a
new `adlai-vault/10_Issues/00_Backlog/STORY-TEST-FLOW.md` specifically for
E2E testing — it will never move to Active/Done and will be reset by the
test teardown.

## Prerequisites

- [[STORY-95]] (Pult wrapper) must be **Done**
- [[STORY-97]] (prompt gates) must be **Done**
- [[STORY-010]] (Unit Test Foundation) must be **Done** — provides pytest fixtures, mock workers, temp dirs

## Acceptance Criteria

- [ ] `backend/tests/integration/test_flow_real_vault.py` exists
- [ ] A fixture story `STORY-TEST-FLOW.md` exists in `adlai-vault/10_Issues/00_Backlog/` for use by flow tests
- [ ] **Flow Test 1 — SYNC Phase (real vault):**
  - Calls `Pult().run("STORY-TEST-FLOW", "sync")` (no mocks)
  - Asserts: exit 0, stdout contains `## PHASE: SYNC`
  - Asserts: SYNC artifact block is written to the fixture story file
  - Asserts: artifact has `status=pending` and valid ISO-8601 `Timestamp:`
  - Teardown: removes the injected artifact block from the fixture story file
- [ ] **Flow Test 2 — SYNC → ENGAGE lifecycle (real vault):**
  - Runs SYNC phase and manually sets `status=ready` on the artifact
  - Calls `Pult().run("STORY-TEST-FLOW", "engage")` (no mocks)
  - Asserts: exit 0, stdout contains `## PHASE: ENGAGE`
  - Asserts: ENGAGE gate passes (no "VALIDATION FAILED" in output)
  - Teardown: restores fixture story to pristine state
- [ ] **Flow Test 3 — Full pipeline with bulk, pult, and prompt_builder nodes (once wired):**
  - Runs a synthetic story through the conductor pipeline
  - Asserts: `bulk_node` executes mechanical tasks when plan contains `mechanical` tags
  - Asserts: `pult_node` publishes artifacts to FLOW vault after commit
  - Asserts: `prompt_builder_service` enriches plan node prompts
  - **Note:** This test is gated behind feature flags; skipped if nodes are not wired
- [ ] **G4 gate:** QA phase must pass (exit 0) before commit_node executes in pipeline tests
- [ ] **G3 gate:** integration tests verify phase artifact gates block execution when predecessor artifacts are missing or pending
- [ ] Tests are skipped (not failed) if `rvc` is not in PATH (use `pytest.mark.skipif`)
- [ ] Tests are skipped if `adlai-vault/` is not found at the expected path
- [ ] Tests are marked `@pytest.mark.integration` and excluded from the unit test gate (unit gate runs `backend/tests/unit` only)
- [ ] Teardown is implemented with `pytest` fixture cleanup — no manual cleanup required after a failed run
- [ ] Tests pass: `uv run pytest backend/tests/integration/test_flow_real_vault.py -v`

## Edge Cases & Error Scenarios

| Scenario | Expected Behaviour |
|----------|-------------------|
| Fixture story file is modified by a previous failed test run | Teardown fixture cleans up before test starts (autouse fixture with pre-test cleanup) |
| `rvc` is available but `rvc context` returns empty | Test skips with `pytest.skip("rvc context empty — vault may be unconfigured")` |
| Git working tree has uncommitted changes from previous runs | Test logs warning but does not fail (tests are read-only except for fixture story) |
| Conductor pipeline is not available (STORY-023 not Done) | Flow Test 3 is skipped via `@pytest.mark.skipif` checking for `bulk_node` in `build_graph` |
| Real vault has 1000+ issues | Tests must complete in <30s; use specific fixture story, not vault scan |

## Non-Functional Requirements

- **Isolation:** Tests must not modify real vault issues (only the fixture story)
- **Performance:** Full test suite must complete in <60s
- **CI Compatibility:** Tests are skipped (not failed) when rvc/vault are unavailable
- **Observability:** Every test run produces a JSON log entry in `LOGS_DIR/integration_tests/` with pass/fail/skip status

## Fixture Story Template

```markdown
---
type: story
status: Backlog
priority: P-test
created: 2026-06-16
id: STORY-TEST-FLOW
title: E2E Flow Test Fixture (do not modify manually)
tags: "[test, fixture, e2e]"
---

# STORY-TEST-FLOW: E2E Flow Test Fixture

This story is a fixture for `test_flow_real_vault.py`.
Do NOT manually edit or move this file.
The test suite writes and cleans up L3 artifacts automatically.

## Objective
Validate that the pult SYNC→ENGAGE→ACT→WRAP lifecycle works against the
real vault layout and real rvc CLI.

## L3 Artifacts
<!-- test teardown cleans up below this line -->
```

## Implementation Notes

The key challenge is test isolation: the flow tests **write** to the vault
(artifact injection), which makes them stateful. Use pytest fixtures with
`yield` + cleanup:

```python
@pytest.fixture(autouse=True)
def clean_fixture_story():
    """Remove L3 artifact blocks from fixture story after each test."""
    yield
    story = FIXTURE_STORY_PATH
    if story.exists():
        content = story.read_text()
        # Strip all l3:phase blocks
        import re
        content = re.sub(
            r'\n<!-- l3:phase=\w+ story=STORY-TEST-FLOW.*?<!-- /l3:phase=\w+ -->\n',
            '',
            content,
            flags=re.DOTALL
        )
        story.write_text(content)
```

## Files to Touch

| File | Action |
|------|--------|
| `backend/tests/integration/test_flow_real_vault.py` | **CREATE** |
| `adlai-vault/10_Issues/00_Backlog/STORY-TEST-FLOW.md` | **CREATE** |

## Definition of Done

- At least 2 E2E flow tests run against real `adlai-vault/`
- SYNC artifact is written and validated against real story file
- SYNC → ENGAGE gate passes with real `rvc` output
- Tests are skipped gracefully if env is not available
- Tests pass in CI when `rvc` and vault are present

## L3 Artifacts
<!-- reserved for phase artifacts written by the agent during execution -->
