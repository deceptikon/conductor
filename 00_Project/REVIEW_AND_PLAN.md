# Architecture Review: RVC Protocol + Conductor Harness

*Review date: 2026-06-28*
*Reviewer: OpenCode (AI-dev assistant)*

---

## 1. RVC (Reglament of Vault Context) — Review

### 1.1 What It Does Well

**Elegant Simplicity.** RVC is a ~430-line CLI plus a ~290-line MCP daemon that turns an Obsidian vault into a fully functional issue tracker. The concept is brilliant: Markdown + YAML frontmatter + folder-based status lanes = zero-database project management. The Obsidian integration is seamless because the "database" IS the filesystem.

**Idempotent Rescanning.** `vault-restructure.py` (696 lines) is the crown jewel. It normalizes frontmatter, auto-wraps STORY/EPIC references in `[[wikilinks]]`, infers domain tags from content keywords, and regenerates `MAP.md` — all idempotently. Running it twice produces zero changes on the second run. This is exactly the right UX for a maintenance tool.

**Context Assembler.** The `rvc context STORY-XX` command recursively resolves wikilinks and dumps linked specs/PRDs. This is the magic that makes AI-assisted development possible — the model gets the issue PLUS all relevant context in one shot.

**Multi-Modal Interface.** Humans use Obsidian GUI; AI assistants use MCP tools (`rvcd.py`); CI/scripts use the CLI. All three write to the same Markdown files. This is local-first done right.

**Vault Discovery.** `find_vault_root()` is well-designed: `.rvc-root` marker → RVC structure check → literal `vault/` fallback. It allows arbitrary vault names, which is essential when you have multiple projects in Obsidian's vault switcher.

### 1.2 Critical Weaknesses (Must Fix)

**Security: `shell=True` Everywhere.** Both `rvc-cli.py` and `rvc-sync.py` use `shell=True` for subprocess calls. In `rvc-cli.py`:
```python
def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, shell=True, cwd=cwd, ...)
```
This is called with string-interpolated paths (`f"git add '{fp}'"`). If a filename contains a single quote, it's a command injection vector. In `sync_after()`, the commit message is passed raw to `f"git commit -m '{msg}'"`. The `rvcd.py` MCP daemon wraps CLI calls in lists, but the underlying CLI still uses `shell=True`.

**Performance: O(n²) Vault Traversal.** `find_file_by_id()` does `os.walk(vault_path)` on *every call*. When `cmd_context()` resolves 10 wikilinks, it walks the vault 10 times. For a 500-file vault, `rvc context` could do 5,000 file traversals. There is **zero caching or indexing**.

**Race Conditions in ID Generation.** `_next_id()` scans all files to find the max number, then returns `max+1`. If two processes create issues simultaneously (e.g., a human in Obsidian and an AI via MCP), they will get the same ID. There is no filesystem locking.

**Ad-Hoc YAML Parsing.** `parse_frontmatter()` splits on `:` and strips quotes manually. It will break on multiline YAML values, values containing colons, or nested structures. A real YAML parser (like `PyYAML`) should be used.

**No Concurrent Access Protection.** What happens when Obsidian auto-saves a file while `rvc issue STORY-01 start` is moving it? The git-sync best-effort warnings are not enough — there should be file-level locking or atomic moves.

**Regex Bug in `EPIC_RE`.** The comment says "only matches EPIC-01..EPIC-09" but the regex is `r'\b(EPIC-\d+)\b'` which matches ANY number. The comment is stale/wrong.

### 1.3 Moderate Weaknesses (Should Fix)

**No Tests.** 1,400+ lines of Python with zero test coverage. The rescan logic especially (tag inference, wikilink wrapping, frontmatter normalization) is complex and would benefit from pytest.

**Error Handling is Print-and-Exit.** Most errors call `print()` then `sys.exit(1)`. This makes programmatic use (via MCP) brittle because the daemon has to parse stderr strings to understand what went wrong.

**MAP.md Generation Uses String Matching, Not Parsing.** `generate_map()` scans `new_content` with `ID_RE.findall()` to build cross-references. This is fragile — it will match IDs inside code blocks, URLs, or frontmatter comments.

**Git Sync is All-or-Nothing.** If `git push` fails, the local state has already been modified (file moved, status changed). There's no rollback mechanism.

### 1.4 Verdict on RVC

**Score: 7/10** — Excellent concept and clean architecture, but production use requires hardening around security (`shell=True`), performance (caching/indexing), and concurrency (locking/atomicity). The core design is sound and the Obsidian integration is genuinely useful. Fix the critical issues and this becomes an 8.5/10 tool.

---

## 2. Conductor — Review

### 2.1 What It Does Well

**Clean LangGraph Architecture.** The pipeline (`plan → review → approve → act → qa → commit`) is expressed as a `StateGraph` with well-defined conditional edges. State is checkpointed to SQLite, making runs durable and resumable. The human-in-the-loop gate uses LangGraph's native `interrupt()`, which is the correct primitive.

**Worker Abstraction is Model-Agnostic.** `workers.py` adapts `claude`, `gemini`, `qwen`, and `opencode` through a common `Worker.run()` interface. Live-streaming stdout/stderr via daemon threads is well-implemented. ANSI stripping and stream-JSON extraction are thoughtful touches.

**Observability.** Per-run logging to `.conductor/logs/<run_id>.{log,stdout,prompt}` makes debugging tractable. The prompt size breakdown (`agents_md / rvc / git / task / rej chars`) logged at INFO is excellent for understanding token usage.

**RVC Integration is Tight.** `_rvc_context()` fetches issue context via CLI, falls back to `~/.local/bin/rvc`, and gracefully returns empty string on failure (pipeline never breaks). The `--extra-context` / `--no-context` flags give users control over token budget.

**Plan Schema with Validation.** `schema.py` defines a DAG-based plan with `validate()` that checks: (1) dependencies exist, (2) no cycles (Kahn's algorithm), (3) non-empty contracts, (4) topo_order consistency. This prevents obviously broken plans from reaching the coder.

**Approval Gate Supports Edit-and-Resubmit.** Humans can not just approve/reject — they can submit an edited plan JSON via `conductor edit`. This is a power-user feature that shows real thought about the human-AI collaboration loop.

### 2.2 Critical Weaknesses (Must Fix)

**QA Node Uses `shell=True`.** Known issue from `AGENTS.md`:
```python
proc = subprocess.run(
    cfg.qa_cmd, cwd=str(cfg.repo), shell=True,
    capture_output=True, text=True, timeout=1800,
)
```
While `qa_cmd` is currently TOML-hardened, this is a latent security vulnerability. The fix (`shlex.split`) is trivial and should be applied immediately.

**PlanReviser Is a Stub.** After `max_qa_retries` failures, `plan_reviser_node` just re-runs the planner with a generic "diagnose this" prompt. It does NOT:
- Parse QA logs to match failures to specific nodes
- Determine if a `test_case` is impossible
- Split oversized nodes
- Escalate to human when the plan is sound but code keeps failing

This is the biggest missing piece for autonomous operation.

**No Parallel Task Execution.** The `act_node` receives the *entire* plan and presumably the worker implements all nodes sequentially. For independent nodes in the DAG, they could be executed in parallel by different workers. The current design wastes latency.

### 2.3 Moderate Weaknesses (Should Fix)

**No Unit Tests.** The `test_fixtures/` directory contains a fake repo for *manual* QA gate testing. There are zero automated tests for `Plan.validate()`, `_extract_stream_json()`, routing decisions, or worker timeout recovery.

**WorkerResult.error Truncation Mismatch.** `AGENTS.md` says stderr is truncated to last 2000 chars, but `workers.py` uses `[-10000:]`. The docs and code are inconsistent.

**`_extract_stream_json` Silently Drops Malformed Lines.** If a worker emits a partial JSON line (e.g., due to a crash), it's dropped without any recovery attempt. For critical outputs, this could lose the only useful error message.

**RVC Context Fetched Twice Per Cycle.** Both `plan_node` and `act_node` call `_rvc_context()`. For a 60-second `rvc context` call, this adds 2 minutes of latency per cycle. The result should be cached in `RunState` after the first fetch.

**Plan Schema is Too Simple.** `expected_output` and `test_case` are plain strings. For complex tasks, structured contracts (JSONSchema, function signatures) would enable stronger validation in the reviewer node and more precise QA matching.

**Commit Node is Naive.** `git add -A && git commit` with no staging review. If the worker created unexpected files (e.g., `__pycache__`, temp files), they get committed. A `.gitignore` check or explicit file list from the plan would be safer.

### 2.4 Verdict on Conductor

**Score: 7.5/10** — Solid orchestration harness with excellent observability and clean separation of concerns. The LangGraph checkpointing and human-in-the-loop gate are well-implemented. The biggest gaps are: (1) PlanReviser stub, (2) lack of tests, (3) sequential act execution. Fix those and this becomes a genuine 9/10 platform for autonomous coding agents.

---

## 3. System-Level Observations (RVC + Conductor Together)

### 3.1 Synergy

The integration is genuinely powerful:
1. Human writes a story in Obsidian → `rvc issue STORY-XX start`
2. `conductor run adlai "..." --issue STORY-XX` fetches context
3. AI plans → human approves → AI implements → QA runs → commits
4. `rvc issue STORY-XX done` moves to Done

This is a **closed loop** from idea to committed code with human oversight at exactly one point (the approval gate). That's the right amount of human-in-the-loop for high-trust, high-stakes work.

### 3.2 Friction Points

**Token Bloat.** `rvc context` routinely produces 60–90K chars. For cheap models like `qwen3-coder-flash`, this consumes context window and increases latency. The `--rvc-mode` flags (`get`/`full`/`off`) partially address this but default to `full`.

**Vault Discovery Mismatch.** Conductor's `_rvc_context()` calls `rvc` binary from the *repo* directory. But `rvc-cli.py`'s `find_vault_root()` walks *up* from CWD. If `repo` is `~/Documents/ADLAI` and the vault is `~/Documents/ADLAI/adlai-vault`, discovery works. But if the vault is outside the repo tree, it fails. The project TOML explicitly specifies `vault` path, but `_rvc_context()` doesn't pass `--path <vault>` to the `rvc` CLI — it relies on auto-discovery from `repo`.

**No Feedback Loop from Conductor to RVC.** When `conductor` QA passes and commits, the RVC issue remains in whatever status it was. There's no automatic `rvc issue STORY-XX review` or `done` transition. The human has to manually update RVC after the pipeline finishes.

---

## 4. Development Plan: Conductor v0.2 & RVC v1.1

### 4.1 Immediate (This Week)

| # | Task | Project | Effort | Impact |
|---|------|---------|--------|--------|
| 1 | Replace `shell=True` with `shlex.split` in QA node | Conductor | 30 min | High (security) |
| 2 | Replace `shell=True` with list commands in `rvc-cli.py` | RVC | 1 hour | High (security) |
| 3 | Cache RVC context in `RunState` (fetch once per cycle) | Conductor | 30 min | Medium (latency) |
| 4 | Fix `EPIC_RE` stale comment | RVC | 5 min | Trivial |

### 4.2 Short-Term (Next 2 Weeks)

| # | Task | Project | Effort | Impact |
|---|------|---------|--------|--------|
| 5 | Build real PlanReviser: parse QA logs, match to nodes, revise contracts | Conductor | 2–3 days | Critical (autonomy) |
| 6 | Add unit tests for `Plan.validate()`, `_extract_stream_json()`, routing | Conductor | 2 days | High (foundation) |
| 7 | Add unit tests for `vault-restructure.py` (tag inference, wikilink wrap) | RVC | 1 day | Medium |
| 8 | Add vault file index/cache to `rvc-cli.py` | RVC | 1 day | High (performance) |
| 9 | Implement atomic ID generation with file locking | RVC | 4 hours | Medium (correctness) |

### 4.3 Medium-Term (Next Month)

| # | Task | Project | Effort | Impact |
|---|------|---------|--------|--------|
| 10 | Parallel DAG execution in `act_node` | Conductor | 3 days | High (latency) |
| 11 | Structured contracts (JSONSchema) for `expected_output`/`test_case` | Conductor | 2 days | High (precision) |
| 12 | Auto-transition RVC issue status after conductor commit | Both | 1 day | Medium (workflow) |
| 13 | Replace ad-hoc YAML parser with `PyYAML` or `ruamel.yaml` | RVC | 4 hours | Medium (robustness) |
| 14 | Add `.gitignore` validation to commit node | Conductor | 2 hours | Low (safety) |

### 4.4 Long-Term (Next Quarter)

| # | Task | Project | Effort | Impact |
|---|------|---------|--------|--------|
| 15 | Graph database backend for RVC (Neo4j / SQLite graph) | RVC | 1–2 weeks | High (scale) |
| 16 | Bulk node wiring for mechanical refactors | Conductor | 2 days | Medium |
| 17 | Self-healing QA: auto-retry flaky tests, detect infra vs code failures | Conductor | 3 days | Medium |
| 18 | Web dashboard for run history, plan visualization, human approval | Conductor | 1–2 weeks | High (UX) |

---

## 5. Priority Ranking (Top 5)

1. **Fix `shell=True` in both projects** — Security trumps everything. Trivial fix, massive risk reduction.
2. **Real PlanReviser** — Without this, the system cannot recover from QA failures autonomously. It's the difference between a demo and a product.
3. **Unit tests for Conductor schema + workers** — The pipeline has complex conditional routing. Tests are needed before adding more features.
4. **Vault indexing in RVC** — `O(n²)` traversal will become painful at scale. A simple JSON index updated on write would solve this.
5. **Parallel DAG execution** — Independent plan nodes should run concurrently. This is a natural evolution of the current architecture.

---

## 6. Personal Opinion

**On RVC:** This is one of the most practical "AI-native" tooling ideas I've seen. The insight that Markdown files in an Obsidian vault can serve as both human-readable documentation AND machine-parseable task database is genuinely clever. The execution is "script-grade" — functional but not hardened. With 2–3 days of security/performance work, it becomes production-grade. The domain-tag inference and MAP.md generation show real product thinking.

**On Conductor:** The LangGraph pipeline is architecturally sound. The checkpointing, resumption, and human gate are implemented correctly. Where it falls short is in the "intelligence" layer — PlanReviser is a stub, there's no failure diagnosis, and the act node treats the plan as a monolith rather than a DAG. These aren't framework issues; they're missing features. The framework is ready. The smarts need to catch up.

**On the Combination:** Together, RVC + Conductor form a credible "AI software engineer" loop. The weakest link is PlanReviser — if QA fails 3 times, a human has to intervene. Fix that, and you have a system that can plan, execute, test, diagnose, and retry with only one human checkpoint. That's genuinely impressive for a ~1,000-line Python harness.

**Bottom line:** Both projects are 80% solutions to 100% problems. The remaining 20% is the hard part (tests, edge cases, failure recovery), but the foundation is solid enough to justify the investment.
