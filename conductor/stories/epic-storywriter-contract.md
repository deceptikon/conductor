# EPIC: Pre-Planning Storywriter & Contract Creation Pipeline

## Summary

Introduce two new subflows **before** the existing `plan` node in
[`pipeline.py`](../pipeline.py): a **Storywriter subflow** that researches
and refines a high-level requirement into a finalized story, and a **Contract
Creation subflow** that transforms the story into a dynamic technical
contract—extending and eventually replacing the static AGENTS.md read at
[`pipeline.py:83`](../pipeline.py:83).

## Context & Motivation

The existing pipeline begins at `plan_node`, which receives a raw `task`
string and operates against a static contract read from `AGENTS.md`. There is
no automated step to:

- Validate that the requirement is well-understood before planning
- Create a traceable RVC vault story entry for the run
- Derive a task-specific technical contract from the story's Definition of Done

This epic adds that lifecycle, keeping the post-planning pipeline
(`review → approve → act → qa → commit`) **entirely unchanged**.

## Proposed Full Pipeline Flow (post-epic)

```
START
  └─► story_research
        └─► story_draft
              └─► story_review ──[valid]──────────► rvc_link
                    └─[invalid, retries < 2]─► story_draft (loop)
                    └─[invalid, retries ≥ 2]─► HitL interrupt()
                                                    └─► story_draft (resume)
                                    rvc_link
                                        └─► contract_propose
                                              └─► contract_validate ──[valid]──► plan
                                                    └─[invalid]─► contract_propose (loop)
plan ──► review ──► approve ──► act ──► qa ──► commit ──► END
```

## Known Design Issues in the Original Proposal (addressed in child stories)

| Issue | Location | Resolution |
|-------|----------|------------|
| `story_draft` used as **both** node name and `RunState` key | Proposal §3 | `RunState` key renamed to `story_text`; node name stays `story_draft` |
| `contract` key overloading — static AGENTS.md vs. dynamic output | Proposal §3 | `contract_proposal` stored separately; merged into `contract` only after `contract_validate` passes (Story 7) |
| `rvc_link` write capability unspecified | Proposal §1 | Explicit acceptance criteria on `rvc create` CLI + output format (Story 5) |
| Missing routing condition — when does Storywriter activate? | Proposal §4 | Conditional edge on `issue_id` absence or explicit `storywriter_mode` flag (Story 9) |
| Proposal uses single `worker_for("storywriter")` for all story nodes | Proposal §3 | Per-node TOML routing keys: `story_research`, `story_draft`, `story_review` (Story 8) |

## Child Stories

| ID | Title | Type |
|----|-------|------|
| [STORY-001](story-001-runstate-schema.md) | Extend `RunState` with story & contract lifecycle fields | Technical |
| [STORY-002](story-002-story-research.md) | `story_research` node: codebase & RVC impact analysis | Functional |
| [STORY-003](story-003-story-draft.md) | `story_draft` node: narrative story generation | Functional |
| [STORY-004](story-004-story-review-retry.md) | `story_review` node: validation, retry loop & HitL escalation | Functional |
| [STORY-005](story-005-rvc-link.md) | `rvc_link` node: create & link RVC vault story entry | Functional |
| [STORY-006](story-006-contract-propose.md) | `contract_propose` node: story-to-technical-contract generation | Functional |
| [STORY-007](story-007-contract-validate.md) | `contract_validate` node: DoD coverage check & contract merge | Functional |
| [STORY-008](story-008-toml-routing.md) | TOML per-node routing for all new pipeline nodes | Technical |
| [STORY-009](story-009-graph-rewiring.md) | `build_graph` rewiring: insert subflows before `plan` | Technical |

## Definition of Done (Epic Level)

1. All 9 child stories are accepted.
2. The full pipeline flow diagram above executes end-to-end on the `adlai` project.
3. `state["contract"]` received by `plan_node` reflects the dynamically created contract when the Storywriter path ran, and still falls back to AGENTS.md when it did not.
4. No regression in any existing pipeline node (`plan`, `review`, `approve`, `act`, `qa`, `commit`).
5. All new nodes emit structured `history` events consistent with the existing [`_log()`](../pipeline.py:89) pattern.
