---
type: story
status: To Do
priority: Medium
started: 2026-06-30
domain: workflow_meta
domain_tags: ["planning", "story"]
---

## Context

Conductor currently builds prompts as **ad-hoc f-strings** inside each node function (`plan_node`, `act_node`, etc. in `pipeline.py`). The `WorkerBackend` protocol (`workers/base.py`) accepts only a single `prompt: str`, passed to CLI backends as a user message. There is no system prompt channel, no template engine, and no centralized project-context injection.

The Storywriter epic adds six new worker-backed nodes that must emit strictly structured output (e.g., `VERDICT: PASS | FAIL`). Without a prompt architecture, we risk inconsistent context injection and unmaintainable inline strings.

Three analyses evaluate alternative approaches:
- [[Analysis Nemotron]]
- [[Analysis Grok]]
- [[Analysis GPT]]

## Objective

Score the three analyses against a common framework, select the best approach (or a hybrid), and produce a concrete proposal for a prompt generation & enrichment system that becomes the single source of truth for all node prompts.

## Evaluation Criteria

Score each variant 1–5:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Backward Compatibility | High | Must not break existing `WorkerBackend` or CLI backends. |
| Testability | High | Prompts must be unit-testable without LLM calls. |
| A/B Testing | Medium | Swapping prompt variants per node without code changes. |
| Context Enrichment | High | Clean injection of `contract`, `git_ctx`, `rvc_ctx`, `task`, and node state. |
| Maintenance | Medium | Fewer locations to edit when tuning a prompt. |
| System Prompt Support | Medium | Separation of persona/instruction (system) from task (user). |

## Three Variants

### Variant A — Minimal Templating
Centralize context gathering in a `_build_prompt(node, template, state)` helper. Store templates as `.txt` files in `prompts/{node}.txt` with Jinja2-style `{{ var }}` substitution.

### Variant B — Protocol Extension
Extend `WorkerBackend.build_cmd()` with an optional `system_prompt: str | None`. Add `system_prompt` and `user_prompt_template` keys to the TOML routing table. Backends that support `--system` (claude, qwen) use it; others fall back to concatenation.

### Variant C — External Prompt Vault
Move all prompts to the RVC vault or a versioned `prompts/` directory. Each file uses YAML frontmatter for variables, a system block, and a user template. Loaded at runtime by a `PromptVault` class.

## Research Tasks

- [ ] Read and score [[Analysis Nemotron]], [[Analysis Grok]], and [[Analysis GPT]] using the criteria above.
- [ ] Document the scoring matrix in a decision record.
- [ ] Select a winning variant or propose a hybrid.
- [ ] Define file structure, class signatures, and any TOML schema changes.
- [ ] Specify how project context (`contract`, `git_ctx`, `rvc_ctx`) flows into the mechanism.
- [ ] Produce a rollout plan: which existing nodes migrate first, which stay on legacy f-strings.

## Final Deliverable

A proposal containing:
1. **Architecture diagram** — node function → prompt builder → `WorkerBackend` → CLI.
2. **File layout** — where templates/system prompts live and how they are discovered.
3. **Code sketch** — signature of the new prompt builder function/class.
4. **TOML schema** — any new routing keys (e.g., `system_prompt = "..."`).
5. **Rollout plan** — lands before, during, or after the Storywriter epic.

## Acceptance Criteria

- [ ] Decision record compares all three variants with scored criteria.
- [ ] One recommended approach is chosen and documented.
- [ ] Proposal includes architecture, file layout, code sketch, TOML schema, and rollout plan.
- [ ] Reviewed and approved by at least one team member before implementation.
- [ ] If the chosen approach requires STORY-001/008 changes, those are identified and ticketed.

## Test Case Requirements

- [ ] A unit test builds a `story_draft` prompt without calling an LLM.
- [ ] A test verifies that missing template variables raise a clear error.
- [ ] A test confirms backward compatibility: existing `plan_node` still works if the new system is not yet adopted.
