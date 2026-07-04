---
type: story
status: To Do
priority: High
started: 2026-06-30
domain: workflow_meta
domain_tags: ["planning", "story"]
---

## Context

The `stories/` folder holds a 9-story epic that inserts a **Storywriter subflow** and **Contract Creation subflow** before the existing `plan` node in `pipeline.py`. The post-epic flow is:

```
START → story_research → story_draft → story_review → rvc_link
  → contract_propose → contract_validate → plan → review → approve
  → act → qa → commit → END
```

This story is a **development gate**. Do not start coding the epic until the acceptance criteria below are satisfied.

### Child Stories

| ID | Title | Type | File |
|----|-------|------|------|
| | STORY-015 | Extend `RunState` with story & contract lifecycle fields | Technical | [`stories/story-015-runstate-schema.md`](stories/story-015-runstate-schema.md) |
| | STORY-016 | `story_research` node: codebase & RVC impact analysis | Functional | [`stories/story-016-story-research.md`](stories/story-016-story-research.md) |
| | STORY-017 | `story_draft` node: narrative story generation | Functional | [`stories/story-017-story-draft.md`](stories/story-017-story-draft.md) |
| | STORY-018 | `story_review` node: validation, retry loop & HitL escalation | Functional | [`stories/story-018-story-review-retry.md`](stories/story-018-story-review-retry.md) |
| | STORY-019 | `rvc_link` node: create & link RVC vault story entry | Functional | [`stories/story-019-rvc-link.md`](stories/story-019-rvc-link.md) |
| | STORY-020 | `contract_propose` node: story-to-technical-contract generation | Functional | [`stories/story-020-contract-propose.md`](stories/story-020-contract-propose.md) |
| | STORY-021 | `contract_validate` node: DoD coverage check & contract merge | Functional | [`stories/story-021-contract-validate.md`](stories/story-021-contract-validate.md) |
| | STORY-022 | TOML per-node routing for all new pipeline nodes | Technical | [`stories/story-022-toml-routing.md`](stories/story-022-toml-routing.md) |
| | STORY-023 | `build_graph` rewiring: insert subflows before `plan` | Technical | [`stories/story-023-graph-rewiring.md`](stories/story-023-graph-rewiring.md) |

### Crucial Findings

1. **Start with STORY-015 + STORY-022.** They are purely additive (zero regression risk) and unlock parallel work by locking the schema and routing config.
2. **Circular dependency:** STORY-016–021 list STORY-023 as a dependency, but STORY-023 needs all node functions to exist first. In practice: write node functions first, wire them last.
3. **No prompt infrastructure exists.** All prompting is ad-hoc f-strings in `pipeline.py`. If prompt quality blocks the storywriter nodes, escalate to STORY-01 (prompt mechanism research).
4. **Breaking change:** STORY-023 defaults `storywriter_mode` to `"auto"`. Callers without `issue_id` will silently enter the Storywriter path. Legacy callers must pass `storywriter_mode = "off"`.
5. **First RVC write:** STORY-019 (`rvc_link`) introduces the first vault write operation. Prior RVC usage (`_rvc_context`) is read-only.

### Priority & Phasing

| Phase | Stories | Goal | Merge Risk |
|-------|---------|------|------------|
| | 1 | **015 + 022** | Schema + routing foundation | Zero |
| | 2 | **016 + 017 + 018** | Storywriter subflow (first user value) | Medium |
| | 3 | **019 + 020 + 021 + 023** | RVC linking, contract creation, graph integration | High |

### RVC Migration Instructions

Before writing code, move these stories from the ephemeral `stories/` folder to the canonical RVC vault:

1. Run `rvc --help` to confirm the correct create/link subcommands.
2. Create an epic issue: `rvc create --title "EPIC: Pre-Planning Storywriter & Contract Creation Pipeline"`.
3. Create child issues for STORY-015 through STORY-023 and link them to the epic.
4. Move the local `stories/*.md` files to `stories/archive/` (or delete them). The `stories/` folder should only hold drafts.
5. Update any cross-references so wiki-links point to RVC vault locations.

## Acceptance Criteria

- [ ] All 9 child stories have been read and their dependencies mapped.
- [ ] Phase 1 (STORY-015 + STORY-022) is ticketed as the first task.
- [ ] A go/no-go decision is recorded on whether STORY-01 (prompt research) blocks Phase 1 or runs in parallel.
- [ ] RVC vault issues exist for the epic and all 9 children.
- [ ] Local `stories/*.md` files are archived or removed.
- [ ] Team is notified that `storywriter_mode = "auto"` is a breaking change.
