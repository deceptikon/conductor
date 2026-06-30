"""Public entry points for creating and launching workers.

Provides :func:`create_worker` (factory) and :func:`launch_worker` (run-and-return)
as the clean integration surface for external callers (pult, scripts, etc.).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from .base import WorkerResult, registry
from .executor import Worker

logger = logging.getLogger("conductor.workers")

DashMode = Literal["sh", "exec", "wt"]


# --------------------------------------------------------------------------- #
# Worker factory
# --------------------------------------------------------------------------- #

def create_worker(
    agentic: str,
    model: str | None = None,
    extra_args: list[str] | None = None,
    read_only: bool = False,
    dash_mode: DashMode = "sh",
) -> Worker:
    """Create a :class:`Worker` by looking up its backend in the registry.

    Args:
        agentic: Backend name (e.g. ``"claude"``, ``"qwen"``). Must be registered.
        model: Optional model override passed to the CLI.
        extra_args: Additional CLI flags.
        read_only: Whether the worker should run in read-only / plan mode.
        dash_mode: Dash TUI pane mode (``"sh"``, ``"exec"``, ``"wt"``).
    """
    backend = registry.get(agentic)
    return Worker(
        backend=backend,
        model=model,
        extra_args=list(extra_args) if extra_args else [],
        read_only=read_only,
        dash_mode=dash_mode,
    )


# --------------------------------------------------------------------------- #
# Default routing — pre-built workers for common pipeline nodes
# --------------------------------------------------------------------------- #

DEFAULT_ROUTING: dict[str, Worker] = {
    "plan":   create_worker("gemini", read_only=True),
    "act":    create_worker("claude"),
    "bulk":   create_worker("qwen"),
    "review": create_worker("claude"),
}


# --------------------------------------------------------------------------- #
# Clean entrypoint — launch a worker with minimal boilerplate
# --------------------------------------------------------------------------- #

def launch_worker(
    worker_name: str,
    prompt: str,
    *,
    model: str | None = None,
    cwd: str | Path | None = None,
    extra_args: list[str] | None = None,
    read_only: bool = False,
    dash_mode: DashMode = "sh",
    timeout: int = 1800,
    env: dict | None = None,
    local_fallback: bool = False,
) -> WorkerResult:
    """Create a worker, run it, return the result.

    This is the single entrypoint for external code (pult, scripts, etc.)
    to invoke an agentic CLI. Example::

        from conductor.workers import launch_worker

        result = launch_worker(
            "qwen",
            "Explain TCP in 10 words",
            model="qwen/qwen3-coder-flash",
            dash_mode="wt",
        )
        print(result.ok, result.text[:200])
    """
    cwd = Path(cwd or Path.cwd())
    worker = create_worker(
        agentic=worker_name,
        model=model,
        extra_args=extra_args,
        read_only=read_only,
        dash_mode=dash_mode,
    )
    return worker.run(prompt, cwd=cwd, timeout=timeout, env=env, local_fallback=local_fallback)
