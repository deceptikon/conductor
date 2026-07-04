---
domain: workflow_meta
domain_tags: ["planning"]

# STORY-020: `contract_propose` Node — Story-to-Technical-Contract Generation

**Epic**: [Pre-Planning Storywriter & Contract Creation Pipeline](epic-storywriter-contract.md)
**Type**: Functional Story

---
> **Parent:** [[VAULT_DOMAINS]]


As a **pipeline operator**,
I want Conductor to automatically derive a task-specific technical contract
from the finalized story,
So that the `plan_node` and `act_node` operate against a precise, run-scoped
contract that reflects this story's Definition of Done rather than the generic
static `AGENTS.md`.

---

## Acceptance Criteria

1. A `contract_propose_node` function is defined inside `build_graph` in
   [`pipeline.py`](../pipeline.py:210).

2. The node resolves its worker via `cfg.worker_for("contract_propose")`.

3. The prompt passed to the worker includes all of:
   - `state["contract"]` (the current AGENTS.md — project-level baseline)
   - `state["story_text"]` (the finalized story)
   - `state["story_research_ctx"]` (codebase impact from STORY-002)
   - If `state["contract_valid"] == False` (retry path): the validation
     feedback stored in `state.get("contract_gaps", "")` must be included
     with a prominent label

4. The prompt instructs the worker to produce a **contract document** in
   AGENTS.md style containing all of:
   - An explicit **Definition of Done** section sourced directly from the
     story's DoD items
   - File/module restrictions (`DO NOT TOUCH` patterns)
   - Coding conventions relevant to the changed area
   - Testing requirements drawn from the story's Acceptance Criteria

5. On success, `state["contract_proposal"]` is populated with the worker's
   output text.

6. On worker failure (`res.ok == False`):
   - If this is the **first attempt**: store the AGENTS.md content as a
     fallback in `contract_proposal` and log a warning
   - If this is a **retry**: retain the previous `contract_proposal` and
     log an error. The node does NOT raise.

7. Raw stdout → `_save_raw_stdout()`, prompt → `_save_prompt()`.

8. A `history` event `"contract_propose"` is appended with fields `worker`,
   `ok`, `cmd`, `retry` (bool: `contract_valid == False` on entry).

9. Returned state keys: `contract_proposal`, `contract_valid` (reset to
   `False` to force re-validation), `status` (set to
   `"contract_validating"`), `history`.

---

## Edge Cases & Considerations

- **`contract_valid` reset**: every entry into `contract_propose_node` must
  reset `contract_valid = False` so `contract_validate_node` always runs a
  fresh check. This prevents a stale True from bypassing validation on retry.
- **Output format**: unlike `plan_node`, the output here is freeform markdown,
  not JSON. There is no schema to parse — the full `res.text` is stored.
- **Length guard**: if `res.text` exceeds `50_000` characters, log a warning.
  The existing AGENTS.md content (reference size ~2–10 KB for adlai) should
  guide the expected ceiling.
- **Critical design clarification**: the original proposal's `contract_proposal`
  is a *staging* contract. It does NOT replace `state["contract"]` at this
  node. Replacement only happens in STORY-007 after validation passes.
- **No RVC write here**: this node does not touch the vault. The contract is
  pipeline-internal until STORY-007 confirms it is valid.

---

## Dependencies

- STORY-015 (`contract_proposal`, `contract_valid` keys in `RunState`)
- STORY-019 (`rvc_link` node precedes this in the graph)
- STORY-022 (TOML routing for `contract_propose` worker)
- STORY-023 (graph edge: `rvc_link → contract_propose`)

