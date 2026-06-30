"""Core abstractions for the worker system.

Defines the :class:`WorkerBackend` protocol, the :class:`WorkerResult` dataclass,
and the :class:`WorkerRegistry` singleton that is the single source of truth for
all known worker types.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger("conductor.workers")


# ------------------------------------------------------------------ #
#  ANSI stripping utility (shared by multiple backends)
# ------------------------------------------------------------------ #

def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


# ------------------------------------------------------------------ #
#  Stream-JSON extraction (shared by Claude and Qwen backends)
# ------------------------------------------------------------------ #

def extract_stream_json(stdout: str, return_dropped: bool = False) -> str | tuple[str, list[str]]:
    """Parse streaming JSON lines produced by Claude / Qwen workers.

    Collects text blocks from ``message.content`` and falls back to a top-level
    ``result`` field if present.
    """
    final: list[str] = []
    dropped: list[str] = []
    result_field: str | None = None
    for line in stdout.splitlines():
        line_s = line.strip()
        if not line_s or not line_s.startswith("{"):
            if line.strip():
                dropped.append(line.rstrip()[:300])
            continue
        try:
            ev = json.loads(line_s)
        except json.JSONDecodeError:
            dropped.append(line_s[:300])
            continue
        if ev.get("type") == "result" and "result" in ev:
            result_field = ev["result"]
        msg = ev.get("message", {})
        for block in (msg.get("content") or []):
            if isinstance(block, dict) and block.get("type") == "text":
                final.append(block.get("text", ""))
        if isinstance(ev.get("content"), str):
            final.append(ev["content"])
    if result_field:
        ret = result_field
    else:
        parsed = "\n".join(final).strip()
        ret = parsed or stdout.strip()
    if return_dropped:
        return ret, dropped
    return ret


# ------------------------------------------------------------------ #
#  Result dataclass
# ------------------------------------------------------------------ #

@dataclass
class WorkerResult:
    """Holds the result of a worker execution."""

    worker: str
    ok: bool
    text: str
    raw: str
    returncode: int
    cmd: str
    error: str = ""


# ------------------------------------------------------------------ #
#  WorkerBackend protocol — the extension point
# ------------------------------------------------------------------ #

@runtime_checkable
class WorkerBackend(Protocol):
    """Protocol for pluggable worker backends.

    Every new worker type (CLI tool, SDK wrapper, etc.) implements this
    interface.  The :class:`Worker` executor delegates command construction
    and output parsing to the backend, keeping the core execution logic
    completely agnostic of worker-specific details.
    """

    name: str

    def build_cmd(
        self,
        prompt: str,
        model: str | None,
        extra_args: list[str],
        read_only: bool,
    ) -> list[str]:
        """Build the command-line argument list for this worker."""
        ...

    def extract_text(self, stdout: str) -> str:
        """Extract clean textual output from raw stdout."""
        ...


# ------------------------------------------------------------------ #
#  Registry — single source of truth
# ------------------------------------------------------------------ #

class WorkerRegistry:
    """Holds all registered :class:`WorkerBackend` instances.

    The module-level :data:`registry` singleton is the default registry used
    by :func:`create_worker` and :func:`launch_worker`.  External code can
    register custom backends via :meth:`register` before calling
    :func:`launch_worker`.
    """

    def __init__(self) -> None:
        self._backends: dict[str, WorkerBackend] = {}

    def register(self, backend: WorkerBackend) -> None:
        """Register a backend.  Overwrites any existing entry with the same name."""
        self._backends[backend.name] = backend
        logger.debug("[registry] registered backend: %s", backend.name)

    def get(self, name: str) -> WorkerBackend:
        """Look up a backend by name.

        Raises:
            KeyError: if *name* is not registered.
        """
        try:
            return self._backends[name]
        except KeyError:
            available = ", ".join(sorted(self._backends))
            raise KeyError(
                f"unknown worker '{name}'. Available: {available or '(none)'}"
            ) from None

    def has(self, name: str) -> bool:
        """Return ``True`` if a backend with *name* is registered."""
        return name in self._backends

    def names(self) -> list[str]:
        """Return a sorted list of all registered backend names."""
        return sorted(self._backends)

    def __repr__(self) -> str:
        return f"<WorkerRegistry {self.names()}>"


# Module-level singleton — used by default throughout the package.
registry = WorkerRegistry()
