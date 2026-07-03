---
domain: workflow_meta
domain_tags: ["planning"]

# STORY-001: Extend `RunState` with Story & Contract Lifecycle Fields

**Epic**: [Pre-Planning Storywriter & Contract Creation Pipeline](epic-storywriter-contract.md)
**Type**: Technical Story

---
> **Parent:** [[VAULT_DOMAINS]]


As a **pipeline developer**,
I want to add the story and contract lifecycle fields to [`RunState`](../pipeline.py:60),
So that all new Storywriter and Contract Creation nodes have a typed, durable
state ledger consistent with the existing checkpoint pattern.

---

## Acceptance Criteria

1. The following keys are added to [`RunState`](../pipeline.py:60) (all `total=False` — optional):

   | Key | Type | Purpose |
   |-----|------|---------|
   | `story_research_ctx` | `str` | Output of the `story_research` node: codebase & RVC impact summary |
   | `story_text` | `str` | Current narrative story content (replaces the ambiguous `story_draft` key name from the original proposal) |
   | `story_retries` | `int` | Number of `story_draft`→`story_review` iterations so far (mirrors `qa_attempts` pattern) |
   | `story_finalized` | `bool` | True once `story_review` accepts the story; gates entry into `rvc_link` |
   | `rvc_story_id` | `str` | The RVC issue ID created by `rvc_link` (e.g. `STORY-91`); written back to `issue_id` if not already set |
   | `contract_proposal` | `str` | Dynamically generated technical contract from `contract_propose` node |
   | `contract_valid` | `bool` | True once `contract_validate` accepts `contract_proposal` |

2. The **existing** `contract: str` key is **not removed or renamed**; it continues to hold the AGENTS.md content read at graph entry and is overwritten with `contract_proposal` only after `contract_valid` is True (enforced in STORY-007, not here).

3. All new keys include an inline comment matching the style of existing keys in [`RunState`](../pipeline.py:60).

4. No existing node (`plan_node`, `act_node`, etc.) references the new keys; adding them is purely additive.

5. `story_retries` uses `int` (not `bool`) to mirror the well-established `qa_attempts: int` + `max_qa_retries` retry-ceiling pattern from [`pipeline.py:418`](../pipeline.py:418).

---

## Edge Cases & Considerations

- **Naming conflict resolved**: the original proposal used `story_draft` as both a node name and a state key. This story uses `story_text` for the state key. The node function is named `story_draft_node` internally and registered as `"story_draft"` in the graph.
- **`rvc_story_id` vs `issue_id`**: If the caller already supplied `issue_id`, `rvc_link` must NOT overwrite it. `rvc_story_id` stores the newly created ID separately; `issue_id` propagation is decided in STORY-005.
- **Security**: No credentials or vault tokens are stored in `RunState`; those remain in environment variables.

---

## Dependencies

None — this is the first story in the epic and has no upstream dependencies.

