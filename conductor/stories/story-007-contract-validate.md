# STORY-007: `contract_validate` Node — DoD Coverage Check & Contract Merge

**Epic**: [Pre-Planning Storywriter & Contract Creation Pipeline](epic-storywriter-contract.md)
**Type**: Functional Story

---

As a **pipeline operator**,
I want the generated contract to be automatically checked against the story's
Definition of Done before it replaces the static AGENTS.md in the active
pipeline state,
So that the `plan_node` and `act_node` never operate against a contract that
silently omits a required DoD item.

---

## Acceptance Criteria

1. A `contract_validate_node` function is defined inside `build_graph` in
   [`pipeline.py`](../pipeline.py:210).

2. The node resolves its worker via `cfg.worker_for("contract_validate")`.

3. The worker is prompted to act as a strict auditor and cross-check
   `state["contract_proposal"]` against `state["story_text"]`. It must:
   - Extract every DoD bullet from the story's **Definition of Done** section
   - Verify each DoD bullet is **explicitly addressed** in `contract_proposal`
   - Emit a structured response:
     ```
     VERDICT: PASS | FAIL
     GAPS: <list of unaddressed DoD items, empty if PASS>
     ```

4. **On PASS (`VERDICT: PASS`)**:
   - `state["contract_valid"]` is set to `True`
   - `state["contract"]` is **overwritten** with `state["contract_proposal"]`
     (this is the merge step — downstream `plan_node` and `act_node` use
     `state["contract"]` exclusively, per [`pipeline.py:217`](../pipeline.py:217)
     and [`pipeline.py:391`](../pipeline.py:391))
   - `state["status"]` is set to `"planning"`
   - The conditional edge routes to `plan_node`

5. **On FAIL (`VERDICT: FAIL`)** — no retry ceiling here; loops directly back:
   - `state["contract_valid"]` is set to `False`
   - `state["contract_gaps"]` is populated with the `GAPS:` section
   - `state["status"]` is set to `"contract_proposing"`
   - The conditional edge routes back to `contract_propose_node`

6. **Infinite loop guard**: if the graph has routed `contract_propose →
   contract_validate → contract_propose` more than `3` times (tracked via a
   new `contract_retries: int` key in `RunState`), the node calls
   `interrupt()` with:
   ```python
   {
       "type": "contract_review_request",
       "contract_proposal": state["contract_proposal"],
       "gaps": state.get("contract_gaps", ""),
       "note": "Contract validation failed 3 times. Provide revised contract text or 'use_agents_md' to fall back to static contract.",
   }
   ```
   - On resume with `{"contract_text": "<revised>"}`: overwrite
     `contract_proposal`, reset `contract_retries`, route back to
     `contract_validate`
   - On resume with `{"use_agents_md": true}`: keep the original AGENTS.md
     in `state["contract"]` (no overwrite), set `contract_valid = True`,
     route to `plan_node`

7. Raw stdout → `_save_raw_stdout()`, prompt → `_save_prompt()`.

8. A `history` event `"contract_validate"` is appended with fields `worker`,
   `ok`, `verdict`, `gaps_count` (int), `contract_merged` (bool), `hitl` (bool).

9. Returned state keys vary by path; all paths return `history`.

---

## Edge Cases & Considerations

- **`state["contract"]` overwrite is the critical design integration point**:
  this is the only node that writes to `state["contract"]`, which is the key
  consumed by all existing downstream nodes. It must be explicitly tested
  that `plan_node` picks up the merged contract in integration tests.
- **Worker parse failure for `VERDICT:`**: treat as `FAIL` — never assume PASS
  when the reviewer output is unstructured.
- **`contract_gaps` key**: not in the original proposal's state table. Must be
  added to `RunState` in STORY-001 as `contract_gaps: str`.
- **`contract_retries` key**: also not in the original proposal. Must be added
  to `RunState` in STORY-001 as `contract_retries: int`. The loop guard value
  of `3` reads from `cfg.max_contract_retries` (default `3`) added in STORY-008.
- **No file write**: the node does NOT write to the physical `AGENTS.md` file.
  `state["contract"]` is the in-memory contract for this run only. Persisting
  the generated contract to disk is an optional post-commit action outside
  this epic's scope.

---

## Dependencies

- STORY-001 (`contract_valid`, `contract_gaps`, `contract_retries` keys)
- STORY-006 (`contract_proposal` populated before this node runs)
- STORY-008 (TOML routing for `contract_validate`; `max_contract_retries` config)
- STORY-009 (conditional edge: PASS → `plan`, FAIL → `contract_propose`,
  `contract_retries ≥ 3` → `interrupt()`)
