"""Worker executor — delegates command construction and output parsing to a
:class:`~conductor.workers.base.WorkerBackend` and handles execution via Dash
or a local subprocess.
"""
from __future__ import annotations

import io
import logging
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .base import WorkerBackend, WorkerResult, _strip_ansi

logger = logging.getLogger("conductor.workers")

DashMode = Literal["sh", "exec", "wt"]

# ------------------------------------------------------------------ #
#  Prompt log-level policy — trimmed by default, full on -v
# ------------------------------------------------------------------ #

_PROMPT_HEAD_INFO = 200    # always shown at INFO
_PROMPT_HEAD_DEBUG = 500   # shown at DEBUG (-v)
_PROMPT_TAIL_DEBUG = 500   # shown at DEBUG (-v)


def _log_prompt(worker_name: str, prompt: str) -> None:
    """Log prompt preview at INFO (trimmed) and DEBUG (longer)."""
    logger.info(
        "[worker:%s] prompt head (first %d chars):\n%s",
        worker_name, _PROMPT_HEAD_INFO, prompt[:_PROMPT_HEAD_INFO],
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "[worker:%s] prompt preview (first %d):\n%s",
            worker_name, _PROMPT_HEAD_DEBUG, prompt[:_PROMPT_HEAD_DEBUG],
        )
        logger.debug(
            "[worker:%s] prompt preview (last %d):\n%s",
            worker_name, _PROMPT_TAIL_DEBUG, prompt[-_PROMPT_TAIL_DEBUG:],
        )


def _log_banner(
    name: str,
    cmd_str: str,
    prompt: str,
    cwd: str | Path,
    timeout: int,
    dash_mode: DashMode,
) -> None:
    """Emit the start-of-run banner."""
    logger.info("[worker:%s] running: %s", name, cmd_str)
    logger.info(
        "[worker:%s]   timeout=%d prompt_len=%d cwd=%s dash_mode=%s",
        name, timeout, len(prompt), cwd, dash_mode,
    )
    _log_prompt(name, prompt)


# ------------------------------------------------------------------ #
#  Dash client lazy import
# ------------------------------------------------------------------ #

def _import_dash_client() -> type:
    """Lazy-import DashClient, adding ~/X/dash to sys.path if needed."""
    try:
        from dash_client import DashClient  # type: ignore[import-not-found]
        return DashClient
    except ImportError:
        candidate = Path.home() / "X" / "dash"
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            from dash_client import DashClient  # type: ignore[import-not-found]
            return DashClient
        raise


# ------------------------------------------------------------------ #
#  Worker executor
# ------------------------------------------------------------------ #

@dataclass
class Worker:
    """Execution context for a single worker run.

    Holds runtime parameters (model, extra args, read-only flag, dash mode) and
    a reference to the :class:`WorkerBackend` that knows how to build commands
    and parse output for this worker type.
    """

    backend: WorkerBackend
    model: str | None = None
    extra_args: list[str] = field(default_factory=list)
    read_only: bool = False
    dash_mode: DashMode = "sh"

    @property
    def name(self) -> str:
        return self.backend.name

    # ------------------------------------------------------------------ #
    # Public run entry point
    # ------------------------------------------------------------------ #
    def run(
        self,
        prompt: str,
        cwd: str | Path,
        timeout: int = 1800,
        env: dict | None = None,
        local_fallback: bool = False,
    ) -> WorkerResult:
        """Execute the worker.

        By default the job is pushed to the Dash TUI.  Set *local_fallback* to
        ``True`` to run the worker as a local subprocess instead (useful for
        debugging or when Dash is unavailable).
        """
        cmd = self.backend.build_cmd(prompt, self.model, self.extra_args, self.read_only)
        cmd_str = shlex.join(cmd)
        _log_banner(self.name, cmd_str, prompt, cwd, timeout, self.dash_mode)

        if not local_fallback:
            return self._run_dash(cmd_str, cwd)
        return self._run_local(cmd, cwd, timeout, env)

    # ------------------------------------------------------------------ #
    # Dash execution
    # ------------------------------------------------------------------ #
    def _run_dash(self, cmd_str: str, cwd: str | Path) -> WorkerResult:
        t0 = time.monotonic()
        try:
            DashClient = _import_dash_client()
            client = DashClient()
            logger.debug(
                "[worker:%s] calling dash_client.push(worker=%r, mode=%r)",
                self.name, self.name, self.dash_mode,
            )
            ok = client.push(
                worker=self.name,
                command=cmd_str,
                cwd=str(cwd),
                mode=self.dash_mode,
            )
            logger.debug(
                "[worker:%s] dash_client.push returned: %r (type=%s)",
                self.name, ok, type(ok).__name__,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error(
                "[worker:%s] dash push THREW after %.1fs: %s (%s)",
                self.name, elapsed, type(exc).__name__, exc,
            )
            return WorkerResult(
                self.name, False, "", "", -1, cmd_str,
                error=f"dash push failed: {exc}",
            )

        elapsed = time.monotonic() - t0
        if ok:
            logger.info("[worker:%s] pushed to dash (%.1fs)", self.name, elapsed)
            return WorkerResult(
                self.name, True, "", "", 0, cmd_str, error="",
            )
        logger.warning(
            "[worker:%s] dash push returned False (%.1fs) — dash not running?",
            self.name, elapsed,
        )
        return WorkerResult(
            self.name, False, "", "", -1, cmd_str,
            error="dash push failed: dash not running?",
        )

    # ------------------------------------------------------------------ #
    # Local subprocess execution (fallback / debug)
    # ------------------------------------------------------------------ #
    def _run_local(
        self,
        cmd: list[str],
        cwd: str | Path,
        timeout: int,
        env: dict | None,
    ) -> WorkerResult:
        t0 = time.monotonic()
        cmd_str = shlex.join(cmd)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError:
            elapsed = time.monotonic() - t0
            logger.error(
                "[worker:%s] binary not found on PATH (%.1fs elapsed)",
                self.name, elapsed,
            )
            return WorkerResult(
                self.name, False, "", "", -127, cmd_str,
                error=f"worker binary not found: {self.name}",
            )

        # --- live-stream stdout + stderr via threads ---
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        stdout_line_count = [0]
        stderr_line_count = [0]

        def _tee(
            stream,
            buf: io.StringIO,
            level: int,
            tag: str,
            counter: list[int],
        ) -> None:
            try:
                for line in stream:
                    line_r = line.rstrip()
                    buf.write(line_r + "\n")
                    counter[0] += 1
                    if line_r.strip():
                        logger.log(
                            level,
                            "[worker:%s] %s %s",
                            self.name, tag, line_r[:500],
                        )
            except Exception as e:
                logger.error("[worker:%s] tee thread died: %s", self.name, e)

        t_out = threading.Thread(
            target=_tee,
            args=(proc.stdout, stdout_buf, logging.INFO, " │", stdout_line_count),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_tee,
            args=(proc.stderr, stderr_buf, logging.WARNING, "ERR│", stderr_line_count),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        # --- wait for completion ---
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - t0
            proc.kill()
            t_out.join(timeout=3)
            t_err.join(timeout=3)
            partial = stdout_buf.getvalue()
            logger.error(
                "[worker:%s] TIMEOUT after %.1fs (timeout=%d, partial stdout=%d chars %d lines):\n%s",
                self.name, elapsed, timeout,
                len(partial or ""), stdout_line_count[0],
                (partial or "")[-2000:],
            )
            return WorkerResult(
                self.name, False, "", partial or "", -1, cmd_str,
                error=f"timeout after {timeout}s",
            )

        t_out.join(timeout=5)
        t_err.join(timeout=5)

        elapsed = time.monotonic() - t0
        stdout = stdout_buf.getvalue()
        stderr_raw = stderr_buf.getvalue()
        text = self.backend.extract_text(stdout)
        ok = proc.returncode == 0

        # --- summary ---
        logger.info(
            "[worker:%s] done in %.1fs: returncode=%d ok=%s "
            "stdout=%d lines/%d chars text=%d chars stderr=%d lines/%d chars",
            self.name, elapsed, proc.returncode, ok,
            stdout_line_count[0], len(stdout), len(text),
            stderr_line_count[0], len(stderr_raw),
        )

        if not ok:
            stderr_final = stderr_raw.strip()
            error_msg = stderr_final[-10000:] or "nonzero exit"
            logger.error(
                "[worker:%s] FAILED after %.1fs:\n%s",
                self.name, elapsed, error_msg,
            )
            return WorkerResult(
                self.name, False, text, stdout,
                proc.returncode, cmd_str, error=error_msg,
            )

        stderr_final = stderr_raw.strip()
        error_msg = stderr_final[-10000:] if stderr_final else ""
        return WorkerResult(
            self.name, True, text, stdout,
            proc.returncode, cmd_str, error=error_msg,
        )
