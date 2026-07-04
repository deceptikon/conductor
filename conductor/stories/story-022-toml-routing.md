---
domain: workflow_meta
domain_tags: ["planning"]

# STORY-022: TOML Per-Node Routing & Config for New Pipeline Nodes

**Epic**: [Pre-Planning Storywriter & Contract Creation Pipeline](epic-storywriter-contract.md)
**Type**: Technical Story

---
> **Parent:** [[VAULT_DOMAINS]]


As a **pipeline operator**,
I want to control which worker and model back each new Storywriter and Contract
Creation node via the project TOML file,
So that I can assign cheaper read-only models to research/review nodes and
stronger models to drafting/contract nodes without touching Python source code.

---

## Acceptance Criteria

### A. `ProjectConfig` dataclass changes ([`projects_config.py:18`](../projects_config.py:18))

1. Two new `int` fields are added to `ProjectConfig`:
   - `max_story_retries: int = 2` (ceiling for `story_review → story_draft` loop)
   - `max_contract_retries: int = 3` (ceiling for `contract_validate → contract_propose` loop)

2. Both fields are loaded from `data["project"]` in `ProjectConfig.load()` with
   `int(p.get("max_story_retries", 2))` and `int(p.get("max_contract_retries", 3))`,
   following the exact pattern of `max_qa_retries` at
   [`projects_config.py:53`](../projects_config.py:53).

### B. `DEFAULT_ROUTING` fallback ([`workers/__init__.py`](../workers/__init__.py))

3. The following node keys are registered in `DEFAULT_ROUTING` (wherever it
   is defined in [`workers/`](../workers/)) with reasonable fallback workers:

   | Node key | Fallback worker | `read_only` |
   |----------|----------------|-------------|
   | `story_research` | same as `plan` default | `True` |
   | `story_draft` | same as `plan` default | `False` |
   | `story_review` | same as `plan` default | `True` |
   | `contract_propose` | same as `plan` default | `False` |
   | `contract_validate` | same as `plan` default | `True` |

4. If `DEFAULT_ROUTING` is not a simple dict (it may be dynamic), the fallback
   lookup in `worker_for()` at [`projects_config.py:56`](../projects_config.py:56)
   must resolve the above keys without raising `KeyError`.

### C. Example TOML entries (added as comments to [`projects/adlai.toml`](../projects/adlai.toml))

5. The `adlai.toml` file gains a documented example block showing all five
   new routing entries as **commented-out examples**, following the style of
   the existing commented examples at [`projects/adlai.toml:41`](../projects/adlai.toml:41):

   ```toml
   # --- storywriter subflow ---
   # [routing.story_research]
   # worker = "qwen"
   # model = "qwen/qwen3-coder-flash"
   # read_only = true
   #
   # [routing.story_draft]
   # worker = "qwen"
   # model = "qwen/qwen3-coder-flash"
   #
   # [routing.story_review]
   # worker = "qwen"
   # model = "qwen/qwen3-coder-flash"
   # read_only = true
   #
   # --- contract creation subflow ---
   # [routing.contract_propose]
   # worker = "qwen"
   # model = "qwen/qwen3-coder-flash"
   #
   # [routing.contract_validate]
   # worker = "qwen"
   # model = "qwen/qwen3-coder-flash"
   # read_only = true
   #
   # max_story_retries = 2
   # max_contract_retries = 3
   ```

---

## Edge Cases & Considerations

- **Original proposal mistake**: the proposal suggested a single
  `worker_for("storywriter")` key for all story nodes. This story corrects
  that to **per-node routing keys** consistent with the existing `plan`, `act`,
  `review` pattern in [`projects/adlai.toml`](../projects/adlai.toml:24).
- **Backward compatibility**: all new TOML keys are optional. Existing
  `adlai.toml` and any other project TOML that does not include them must
  continue to load without error (relying on `DEFAULT_ROUTING` fallbacks).
- **`read_only` flag semantics**: `read_only = true` in the TOML maps to
  `--approval-mode plan` for qwen/claude workers. Research and review nodes
  should always be read-only; draft and propose nodes should not be.

---

## Dependencies

- STORY-015 (new `RunState` keys drive the need for config ceilings)
- No other story — this is a prerequisite for stories 16–21 to call
  `cfg.worker_for(...)` without `KeyError`

