"""conductor CLI — drive a project task through the pipeline.

Usage:
  # start a run (pauses at the approval gate, prints the plan, persists state)
  uv run conductor run adlai "Add a docstring to ingest_pdf in backend/ingest.py" --type docs

  # list runs / show one
  uv run conductor status <run_id>

  # approve, reject, or edit a paused run (resumes from the checkpoint)
  uv run conductor approve <run_id>
  uv run conductor reject  <run_id> --note "use the streaming parser instead"
  uv run conductor edit    <run_id> --plan-file revised_plan.json

  # dry-run the graph wiring without invoking any CLI worker
  uv run conductor selftest adlai
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .pipeline import build_graph, _plan_to_json
from .projects_config import ProjectConfig

# Use repo-local state directory — no ~/.hermes linkage.
STATE_DIR = Path(__file__).parent.parent / ".conductor"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CKPT_DB = STATE_DIR / "checkpoints.sqlite"
LEDGER_DIR = STATE_DIR / "runs"
LEDGER_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("conductor")

LOG_DIR = STATE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _setup_logging(verbose: bool = False, run_id: str | None = None):
    """Configure logging: console (always) + per-run file (when run_id given).

    Logs are written to .conductor/logs/<run_id>.log for persistence
    across sessions. This supports the multi-agent workflow where later agents
    need to inspect what earlier agents did.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(name)s %(levelname)s: %(message)s"
    datefmt = "%H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if _setup_logging is called multiple times
    for h in list(root.handlers):
        root.removeHandler(h)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console)

    # Per-run file handler — enables post-mortem across agent sessions
    if run_id:
        log_path = LOG_DIR / f"{run_id}.log"
        file_handler = logging.FileHandler(str(log_path), mode="a")
        file_handler.setLevel(logging.DEBUG)  # Always capture DEBUG to file
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(file_handler)
        logger.debug("[logging] writing to %s", log_path)


def _saver():
    # check_same_thread=False so the connection survives across CLI invocations
    conn = sqlite3.connect(str(CKPT_DB), check_same_thread=False)
    return SqliteSaver(conn)


def _write_ledger(run_id: str, snapshot: dict) -> Path:
    p = LEDGER_DIR / f"{run_id}.json"
    p.write_text(json.dumps(snapshot, indent=2, default=str))
    return p


def _render(state: dict) -> str:
    lines = [
        f"status      : {state.get('status')}",
        f"qa_passed   : {state.get('qa_passed')}",
        f"qa_attempts : {state.get('qa_attempts', 0)}",
        f"commit_sha  : {state.get('commit_sha') or '-'}",
    ]
    plan = state.get("plan")
    if plan is not None:
        # plan may be a Plan dataclass or a dict (after json round-trip)
        if hasattr(plan, "id"):
            lines.append(f"\n--- PLAN ({plan.id} v{plan.version}) ---")
            lines.append(_plan_to_json(plan))
        else:
            lines.append(f"\n--- PLAN ---\n{json.dumps(plan, indent=2, default=str)[:4000]}")
    return "\n".join(lines)


def cmd_run(args):
    run_id = args.run_id or uuid.uuid4().hex[:12]
    _setup_logging(args.verbose, run_id=run_id)
    # --bg: fire-and-forget via subprocess, return run_id immediately
    if args.bg:
        log_path = LOG_DIR / f"{run_id}.log"
        # Re-invoke ourselves without --bg, redirecting output to log file
        cmd = [
            sys.executable, "-m", "conductor", "run",
            args.project, args.task,
            "--type", args.type,
            "--run-id", run_id,
        ]
        if args.issue:
            cmd += ["--issue", args.issue]
        if args.rvc_mode != "full":
            cmd += ["--rvc-mode", args.rvc_mode]
        with open(log_path, "w") as fp:
            subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT)
        print(f"run_id: {run_id}")
        print(f"log   : {log_path}")
        print()
        print(f">>> Background run started. Monitor with:")
        print(f">>>   uv run conductor logs {run_id} -f")
        print(f">>>   uv run conductor approve {run_id}  (or reject / edit)")
        return

    cfg = ProjectConfig.load(args.project)
    cfg_ctx = {"configurable": {"thread_id": run_id}}
    saver = _saver()
    graph = build_graph(cfg).compile(checkpointer=saver)
    init: dict = {
        "project": cfg.name,
        "run_id": run_id,
        "task": args.task,
        "task_type": args.type,
        "issue_id": args.issue or "",
        "rvc_mode": args.rvc_mode,
        "qa_attempts": 0,
        "history": [],
    }
    logger.info("[run] starting run_id=%s project=%s", run_id, cfg.name)
    logger.debug("[run] initial state: task=%s type=%s issue=%s",
                  args.task, args.type, args.issue or "(none)")
    result = graph.invoke(init, cfg_ctx)
    state = graph.get_state(cfg_ctx)
    snap = dict(state.values)
    _write_ledger(run_id, snap)
    final_status = snap.get("status", "?")
    logger.info("[run] completed run_id=%s status=%s", run_id, final_status)
    print(f"\nrun_id: {run_id}")
    # if interrupted at approval, result carries __interrupt__
    if "__interrupt__" in result:
        print("\n>>> PAUSED at approval gate. Review the plan below, then:")
        print(f">>>   uv run conductor approve {run_id}")
        print(f">>>   uv run conductor reject  {run_id} --note '...'")
        print(f">>>   uv run conductor edit    {run_id} --plan-file revised.json\n")
        print(_render(snap))
    else:
        print(_render(snap))


def _resume(run_id: str, payload: dict):
    # We need the project to rebuild the graph; read it from the ledger.
    ledger = LEDGER_DIR / f"{run_id}.json"
    if not ledger.exists():
        sys.exit(f"no such run: {run_id}")
    proj = json.loads(ledger.read_text()).get("project")
    cfg = ProjectConfig.load(proj)
    cfg_ctx = {"configurable": {"thread_id": run_id}}
    saver = _saver()
    graph = build_graph(cfg).compile(checkpointer=saver)
    logger.info("[resume] run_id=%s payload_keys=%s", run_id, list(payload.keys()))
    logger.debug("[resume] payload=%s", json.dumps(payload, default=str)[:1000])
    result = graph.invoke(Command(resume=payload), cfg_ctx)
    state = graph.get_state(cfg_ctx)
    snap = dict(state.values)
    _write_ledger(run_id, snap)
    final_status = snap.get("status", "?")
    logger.info("[resume] completed run_id=%s status=%s", run_id, final_status)
    print(f"run_id: {run_id}")
    if "__interrupt__" in result:
        print(">>> PAUSED again at approval gate (replan).")
    print(_render(snap))


def cmd_approve(args):
    _setup_logging(getattr(args, "verbose", False), run_id=args.run_id)
    _resume(args.run_id, {"approved": True})


def cmd_reject(args):
    _setup_logging(getattr(args, "verbose", False), run_id=args.run_id)
    _resume(args.run_id, {"approved": False, "note": args.note or ""})


def cmd_edit(args):
    _setup_logging(getattr(args, "verbose", False), run_id=args.run_id)
    plan_file = Path(args.plan_file)
    if not plan_file.exists():
        sys.exit(f"plan file not found: {plan_file}")
    try:
        edited = json.loads(plan_file.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"invalid JSON in plan file: {e}")
    _resume(args.run_id, {"edited_plan": edited})


def cmd_status(args):
    ledger = LEDGER_DIR / f"{args.run_id}.json"
    if not ledger.exists():
        sys.exit(f"no such run: {args.run_id}")
    snap = json.loads(ledger.read_text())
    print(_render(snap))
    print("\n--- HISTORY ---")
    for e in snap.get("history", []):
        print("  ", json.dumps(e, default=str))


def cmd_list(args):
    """List all runs with status."""
    if not LEDGER_DIR.exists():
        print("No runs yet.")
        return
    runs = sorted(LEDGER_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        print("No runs yet.")
        return
    print(f"{'RUN_ID':<14} {'STATUS':<20} {'PROJECT':<12} {'TASK'}")
    print("-" * 80)
    for p in runs:
        try:
            snap = json.loads(p.read_text())
        except Exception as e:
            logger.error("[list] skipping corrupted ledger %s: %s", p.name, e)
            continue
        rid = p.stem[:12]
        status = snap.get("status", "?")[:19]
        proj = snap.get("project", "?")[:11]
        task = (snap.get("task", "") or "")[:50]
        print(f"{rid:<14} {status:<20} {proj:<12} {task}")


def cmd_logs(args):
    """Show or follow run logs (reads ledger + worker output files)."""
    ledger = LEDGER_DIR / f"{args.run_id}.json"
    if not ledger.exists():
        sys.exit(f"no such run: {args.run_id}")
    snap = json.loads(ledger.read_text())
    print(_render(snap))
    print("\n--- HISTORY ---")
    for e in snap.get("history", []):
        print("  ", json.dumps(e, default=str))
    # Also show the detailed log file if it exists
    log_file = LOG_DIR / f"{args.run_id}.log"
    if log_file.exists() and log_file.stat().st_size > 0:
        print(f"\n--- DETAILED LOG ({log_file}) ---")
        print(log_file.read_text()[-8000:])  # tail last 8KB
    elif not args.follow:
        print(f"\n(no detailed log at {log_file})")
    # If followed, poll for updates
    if args.follow:
        import time
        last_mtime = ledger.stat().st_mtime
        try:
            while True:
                time.sleep(1)
                try:
                    new_mtime = ledger.stat().st_mtime
                except FileNotFoundError:
                    logger.debug("[logs] ledger vanished, stopping follow")
                    break
                if new_mtime > last_mtime:
                    last_mtime = new_mtime
                    snap2 = json.loads(ledger.read_text())
                    new_status = snap2.get("status", "")
                    if new_status != snap.get("status"):
                        print(f"\n>>> STATUS: {snap.get('status')} → {new_status}")
                        snap = snap2
                    # Print new history entries
                    old_len = len(snap.get("history", []))
                    new_history = snap2.get("history", [])
                    for e in new_history[old_len:]:
                        print("  ", json.dumps(e, default=str))
                    if new_status in ("done", "qa_failed", "rejected"):
                        print(f"\n>>> Run finished: {new_status}")
                        break
        except KeyboardInterrupt:
            print("\n(stopped following)")


def cmd_selftest(args):
    """Compile the graph + load config without invoking any worker."""
    _setup_logging(args.verbose, run_id=f"selftest-{args.project}")
    cfg = ProjectConfig.load(args.project)
    saver = _saver()
    graph = build_graph(cfg).compile(checkpointer=saver)
    print("OK: project config + graph compiled")
    print(f"  project : {cfg.name}")
    print(f"  repo    : {cfg.repo}")
    print(f"  vault   : {cfg.vault}")
    print(f"  qa_cmd  : {cfg.qa_cmd}")
    print(f"  agents  : {cfg.agents_md} (exists={cfg.agents_md.exists()})")
    for node in ("plan", "act", "bulk", "review"):
        w = cfg.worker_for(node)
        model_info = f" model={w.model}" if w.model else ""
        print(f"  route[{node:6}] -> {w.name} (read_only={w.read_only}){model_info}")
    print(f"  nodes   : {list(graph.get_graph().nodes)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="conductor")
    p.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="start a pipeline run")
    r.add_argument("project"); r.add_argument("task")
    r.add_argument("--type", default="feat", help="conventional-commit type")
    r.add_argument("--issue", default="", help="RVC/vault issue id")
    r.add_argument("--rvc-mode", default="full", choices=["full", "get", "off"],
                   help="RVC context mode: full (issue+links), get (issue only), off (skip)")
    r.add_argument("--run-id", default="")
    r.add_argument("--bg", action="store_true", help="fire-and-forget: return run_id immediately, detach")
    r.set_defaults(fn=cmd_run)

    a = sub.add_parser("approve", help="approve a paused run"); a.add_argument("run_id"); a.set_defaults(fn=cmd_approve)
    j = sub.add_parser("reject", help="reject a paused run"); j.add_argument("run_id"); j.add_argument("--note", default="")
    j.set_defaults(fn=cmd_reject)
    e = sub.add_parser("edit", help="submit an edited plan for a paused run")
    e.add_argument("run_id")
    e.add_argument("--plan-file", required=True, help="path to revised Plan JSON file")
    e.set_defaults(fn=cmd_edit)
    s = sub.add_parser("status", help="show run status"); s.add_argument("run_id"); s.set_defaults(fn=cmd_status)
    l = sub.add_parser("list", help="list all runs"); l.set_defaults(fn=cmd_list)
    g = sub.add_parser("logs", help="show or follow run logs"); g.add_argument("run_id")
    g.add_argument("-f", "--follow", action="store_true", help="follow live")
    g.set_defaults(fn=cmd_logs)
    t = sub.add_parser("selftest", help="dry-run graph compilation"); t.add_argument("project")
    t.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    t.set_defaults(fn=cmd_selftest)

    args = p.parse_args(argv)
    # Each command handler is responsible for calling _setup_logging so that
    # per-run file handlers are wired with the correct run_id.
    args.fn(args)


if __name__ == "__main__":
    main()
