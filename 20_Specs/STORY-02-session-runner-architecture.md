---
domain: workflow_meta
domain_tags: ["planning"]

# STORY-02 Session Runner — Architecture Plan

## Goal

Design a **temporary, standalone Python module** (`story_session.py`) that automates the manual execution ritual for STORY-02's 9 child stories. It must:

1. Live **outside** the main `pipeline.py` flow (temporary, not wired into LangGraph).
2. **Reuse** existing conductor classes/methods where possible (`RunState`, `ProjectConfig`, `Worker`, `_git_context`, `_rvc_context`, `_save_raw_stdout`, `_save_prompt`, `_log`).
3. **Mock** what does not yet exist (new `RunState` keys, new TOML routing entries, new node functions) with temporary stubs that mirror the eventual pipeline behavior.
4. Keep **all artifacts** in RVC vault folders (`90_Assets/`, `10_Issues/`).
5. Be **simple enough** to delete once STORY-009 wires the real pipeline.

---
> **Parent:** [[VAULT_DOMAINS]]


## Module Location & Lifecycle

```
conductor/
  story_session.py          <-- temporary module (this plan)
  pipeline.py               <-- existing (imported for helpers)
  projects_config.py        <-- existing (imported for ProjectConfig)
  workers/                  <-- existing (imported for launch_worker)
```

**Lifecycle:**
- Born: now (STORY-02 execution phase)
- Dies: after STORY-009 merges and the real pipeline handles storywriter subflow
- Migration: any valuable helper methods move into `pipeline.py` or `projects_config.py`

---

## Reuse vs Mock Matrix

| Existing Component | Reuse? | How | Mock if missing |
|-------------------|--------|-----|---------------|
| `RunState` (TypedDict) | **Partial** | Import from `pipeline.py`, extend with new keys at runtime | `dict` fallback if import fails |
| `ProjectConfig` | **Yes** | `ProjectConfig.load("adlai")` | Hard-coded defaults |
| `ProjectConfig.worker_for()` | **Yes** | Call for `"plan"`, `"act"`, etc. | Print warning, use `launch_worker` directly |
| `Worker` / `launch_worker()` | **Yes** | For actual LLM calls during story execution | `print("[MOCK] would call worker")` |
| `_git_context()` | **Yes** | Import from `pipeline.py` | Return `"(git unavailable)"` |
| `_rvc_context()` | **Yes** | Import from `pipeline.py` | Return `""` |
| `_save_raw_stdout()` | **Yes** | Import from `pipeline.py` | Write to `../90_Assets/` manually |
| `_save_prompt()` | **Yes** | Import from `pipeline.py` | Write to `../90_Assets/` manually |
| `_log()` | **Yes** | Import from `pipeline.py` | Append to local list |
| `_read_contract()` | **Yes** | Import from `pipeline.py` | Read `AGENTS.md` directly |
| New `RunState` keys (`story_text`, `contract_proposal`, etc.) | **Mock** | Treat as plain dict keys | N/A |
| New TOML routing (`story_research`, `story_draft`, etc.) | **Mock** | Add to `DEFAULT_ROUTING` at runtime or use `launch_worker` directly | N/A |
| New node functions (`story_research_node`, etc.) | **Mock** | `story_session.py` defines them as standalone functions, not inside `build_graph` | N/A |

---

## Module Structure

```python
# story_session.py
"""Temporary STORY-02 session runner.

Automates pre-flight / post-flight for the 9 child stories.
Uses existing pipeline helpers where possible; mocks what is not yet wired.
"""

# ------------------------------------------------------------------ #
# 1. IMPORTS — existing conductor code
# ------------------------------------------------------------------ #
from conductor.pipeline import (
    RunState,
    _git_context,
    _rvc_context,
    _save_raw_stdout,
    _save_prompt,
    _log,
    _read_contract,
)
from conductor.projects_config import ProjectConfig
from conductor.workers import launch_worker, create_worker, DEFAULT_ROUTING

# ------------------------------------------------------------------ #
# 2. MOCK / TEMPORARY EXTENSIONS
# ------------------------------------------------------------------ #
# New RunState keys are just dict keys — no schema change needed for temp module.
# New routing: inject into DEFAULT_ROUTING at runtime or bypass it.

# ------------------------------------------------------------------ #
# 3. VAULT PATHS
# ------------------------------------------------------------------ #
VAULT_DIR = Path(__file__).parent.parent  # up from conductor/
ASSETS_DIR = VAULT_DIR / "90_Assets"
ISSUES_DIR = VAULT_DIR / "10_Issues"
STORIES_DIR = Path(__file__).parent / "stories"
RUNSTATE_PATH = ASSETS_DIR / "story-02-runstate.md"

# ------------------------------------------------------------------ #
# 4. STORY METADATA (dependencies, files, phase)
# ------------------------------------------------------------------ #
STORY_META = { ... }  # same as in ritual spec

# ------------------------------------------------------------------ #
# 5. RUNSTATE I/O
# ------------------------------------------------------------------ #
def _parse_runstate() -> dict: ...
def _write_runstate(state: dict) -> None: ...

# ------------------------------------------------------------------ #
# 6. PRE-FLIGHT / POST-FLIGHT CLI
# ------------------------------------------------------------------ #
def cmd_init(args): ...
def cmd_start(args): ...
def cmd_finish(args): ...

# ------------------------------------------------------------------ #
# 7. MOCK NODE FUNCTIONS (temporary stand-ins for pipeline.py nodes)
# ------------------------------------------------------------------ #
# These mirror what STORY-002 through STORY-007 will eventually add to build_graph.
# They are standalone functions here, not closures inside build_graph.

def story_research_node(state: dict, cfg: ProjectConfig) -> dict:
    """Mock of STORY-002 node."""
    ...

def story_draft_node(state: dict, cfg: ProjectConfig) -> dict:
    """Mock of STORY-003 node."""
    ...

def story_review_node(state: dict, cfg: ProjectConfig) -> dict:
    """Mock of STORY-004 node."""
    ...

def rvc_link_node(state: dict, cfg: ProjectConfig) -> dict:
    """Mock of STORY-005 node."""
    ...

def contract_propose_node(state: dict, cfg: ProjectConfig) -> dict:
    """Mock of STORY-006 node."""
    ...

def contract_validate_node(state: dict, cfg: ProjectConfig) -> dict:
    """Mock of STORY-007 node."""
    ...

# ------------------------------------------------------------------ #
# 8. MAIN
# ------------------------------------------------------------------ #
def main(): ...
```

---

## Mock Node Function Design

Each mock node follows the **same signature** as the real node will have inside `build_graph`:

```python
def <node>_node(state: dict, cfg: ProjectConfig) -> dict:
    """Returns state updates (delta), not full state."""
```

### `story_research_node` (STORY-002 mock)

```python
def story_research_node(state, cfg):
    # Reuse: _git_context, _rvc_context, _save_raw_stdout, _save_prompt, _log
    # Mock: worker resolution (no TOML entry yet -> use launch_worker directly)
    
    git_ctx = _git_context(cfg.repo)
    issue_ctx = _rvc_context(state.get("issue_id", ""), cfg.repo, state.get("rvc_mode", "full"))
    
    prompt = f"...research prompt using git_ctx, issue_ctx, task..."
    
    # Mock routing: since TOML may not have story_research yet, call launch_worker directly
    worker_name = "gemini"  # temporary default
    res = launch_worker(worker_name, prompt, read_only=True, timeout=300)
    
    _save_raw_stdout(state["run_id"], res.raw, "story_research")
    _save_prompt(state["run_id"], prompt, "story_research")
    
    return {
        "story_research_ctx": res.text if res.ok else f"(research failed: {res.error})",
        "status": "story_drafting",
        "history": _log(state, "story_research", worker=worker_name, ok=res.ok, cmd=res.cmd, ctx_len=len(res.text)),
    }
```

### `story_draft_node` (STORY-003 mock)

```python
def story_draft_node(state, cfg):
    contract = state.get("contract", _read_contract(cfg))
    research = state.get("story_research_ctx", "")
    task = state["task"]
    feedback = state.get("story_review_feedback", "")
    
    prompt = f"...draft prompt using contract, research, task, feedback..."
    
    worker_name = "claude"  # temporary default
    res = launch_worker(worker_name, prompt, timeout=300)
    
    _save_raw_stdout(state["run_id"], res.raw, "story_draft")
    _save_prompt(state["run_id"], prompt, "story_draft")
    
    return {
        "story_text": res.text if res.ok else state.get("story_text", ""),
        "status": "story_reviewing",
        "history": _log(state, "story_draft", worker=worker_name, ok=res.ok, cmd=res.cmd, retry=state.get("story_retries", 0) > 0),
    }
```

### `story_review_node` (STORY-004 mock)

```python
def story_review_node(state, cfg):
    story = state.get("story_text", "")
    retries = state.get("story_retries", 0)
    max_retries = 2  # temporary; real will use cfg.max_qa_retries or similar
    
    # Simple heuristic validation (or call worker)
    valid = all(section in story for section in ["Title:", "As a", "I want to", "So that", "Acceptance Criteria:"])
    
    if valid:
        return {
            "story_finalized": True,
            "status": "contract_proposing",
            "history": _log(state, "story_review", ok=True, retries=retries),
        }
    elif retries < max_retries:
        return {
            "story_finalized": False,
            "story_retries": retries + 1,
            "story_review_feedback": "Story format incomplete. Please add missing sections.",
            "status": "story_drafting",  # graph will route back
            "history": _log(state, "story_review", ok=False, retries=retries + 1),
        }
    else:
        return {
            "story_finalized": False,
            "status": "story_failed",
            "history": _log(state, "story_review", ok=False, retries=retries, escalated=True),
        }
```

### `rvc_link_node` (STORY-005 mock)

```python
def rvc_link_node(state, cfg):
    # Reuse: subprocess to call rvc CLI
    # Mock: no real write if rvc unavailable; just log intent
    
    story_text = state.get("story_text", "")
    title = story_text.split("\n")[0].replace("Title: ", "").strip() if "Title:" in story_text else "Untitled Story"
    
    # Attempt RVC create
    rvc_id = ""
    try:
        proc = subprocess.run(
            ["rvc", "create", "--title", title],
            capture_output=True, text=True, timeout=30, cwd=cfg.repo
        )
        if proc.returncode == 0:
            # Parse ID from output (mock: assume last word is ID)
            rvc_id = proc.stdout.strip().split()[-1]
    except Exception as e:
        logger.warning("[rvc_link] rvc create failed: %s", e)
        rvc_id = f"MOCK-{state['run_id']}"
    
    return {
        "rvc_story_id": rvc_id,
        "status": "contract_proposing",
        "history": _log(state, "rvc_link", rvc_id=rvc_id),
    }
```

### `contract_propose_node` (STORY-006 mock)

```python
def contract_propose_node(state, cfg):
    contract = state.get("contract", _read_contract(cfg))
    story = state.get("story_text", "")
    research = state.get("story_research_ctx", "")
    rvc_id = state.get("rvc_story_id", "")
    
    prompt = f"...contract propose prompt..."
    
    worker_name = "claude"
    res = launch_worker(worker_name, prompt, timeout=600)
    
    _save_raw_stdout(state["run_id"], res.raw, "contract_propose")
    _save_prompt(state["run_id"], prompt, "contract_propose")
    
    return {
        "contract_proposal": res.text if res.ok else "",
        "status": "contract_validating",
        "history": _log(state, "contract_propose", worker=worker_name, ok=res.ok),
    }
```

### `contract_validate_node` (STORY-007 mock)

```python
def contract_validate_node(state, cfg):
    proposal = state.get("contract_proposal", "")
    story = state.get("story_text", "")
    
    # Simple heuristic: check if proposal mentions acceptance criteria from story
    valid = len(proposal) > 200 and "Acceptance Criteria" in proposal
    
    if valid:
        return {
            "contract_valid": True,
            "contract": proposal,  # overwrite AGENTS.md content in state
            "status": "planning",
            "history": _log(state, "contract_validate", ok=True),
        }
    else:
        return {
            "contract_valid": False,
            "status": "contract_proposing",  # graph routes back
            "history": _log(state, "contract_validate", ok=False),
        }
```

---

## CLI Design

```bash
# Initialize runstate
python -m conductor.story_session init

# Start a story session (pre-flight)
python -m conductor.story_session start STORY-002

# Run a mock node directly (for testing / iterative development)
python -m conductor.story_session run story_research --project adlai --task "Add user auth"

# Finish a story session (post-flight)
python -m conductor.story_session finish STORY-002

# Show current runstate
python -m conductor.story_session status
```

### `init`

- Creates `../90_Assets/story-02-runstate.md` from template
- Sets `started`, `current_phase`, `status = "init"`

### `start STORY-XXX`

- Parses runstate
- Checks dependencies (all deps must be `done`)
- Prints:
  - Files to read
  - State keys this story consumes (with current values)
  - Current phase
- **Does NOT run code** — this is for the human to open an agentic session

### `run <node_name>` (optional, for testing)

- Loads `ProjectConfig`
- Builds a minimal `state` dict from runstate + CLI args
- Calls the mock node function
- Prints returned delta
- **Does NOT update runstate** (dry-run)

### `finish STORY-XXX`

- Prompts for output keys (or reads them from a `--delta-file`)
- Updates runstate tracker table
- Appends history
- Advances phase if all stories in current phase are done

### `status`

- Pretty-prints the runstate
- Shows which stories are blocked, which are ready

---

## Artifact Flow

```
Agentic Session
      |
      v
+-----+-----+
|  start    |  <-- reads runstate, checks deps, prints context
+-----+-----+
      |
      v
[Human + LLM coding]
      |
      v
+-----+-----+
|  finish   |  <-- prompts for outputs, writes runstate
+-----+-----+
      |
      v
+-----+-----+
|  runstate |  <-- ../90_Assets/story-02-runstate.md
+-----+-----+
      |
      v
+-----+-----+
| artifacts |  <-- ../90_Assets/story-02-artifacts/<story>/
+-----------+      (prompts, stdout, handoff notes)
```

---

## Deletion / Migration Path

When STORY-009 merges:

1. **Delete** `story_session.py` entirely.
2. **Move** any refined helper logic into `pipeline.py` (e.g., improved prompt templates).
3. **Archive** `../90_Assets/story-02-runstate.md` to `../99_Archive/`.
4. **Keep** `../90_Assets/story-02-artifacts/` as historical record.

The mock node functions in `story_session.py` serve as **reference implementations** for the real nodes that will be added to `build_graph` in STORY-009.

---

## Open Questions

1. **Should `run` command actually call workers?** It requires a valid `ProjectConfig` and API keys. Maybe default to `--dry-run` mode.
2. **Should we support `--auto-finish`?** If the agentic session produces a JSON delta file, `finish` could read it instead of prompting interactively.
3. **How to handle STORY-001 (schema change)?** The mock nodes use plain dict keys; the real `RunState` TypedDict update in STORY-001 will make them typed. No conflict.
4. **How to handle STORY-008 (TOML routing)?** The mock nodes hardcode worker names (`gemini`, `claude`). Once TOML routing exists, the mock nodes can call `cfg.worker_for("story_research")` instead.

