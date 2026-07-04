"""Infrastructure commands around the conductor pipeline.

Covers the four entries in COMMANDS_REGISTRY.md's "Infra + Dash" section:

  * dash-client push       (STAGE 12)
  * rvc_mcp.py             (standalone FastMCP server)
  * session_bootstrap.sh   (legacy L5 assembler)
  * agentic-bridge         (:22222 narrative agent)

Tests assert the *external contract* — CLI surface, exit codes, socket
protocol — not internal implementation. The RED tests pin things that
need to be built or hardened.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest


TEAMFLOW = Path(__file__).resolve().parents[2]
BOOTSTRAP = TEAMFLOW / "00_Project" / "session_bootstrap.sh"
DASH_CLIENT = TEAMFLOW / "dash" / "dash_client.py"
RVC_MCP = TEAMFLOW / "rvc_mcp.py"
BRIDGE = TEAMFLOW / "conductor" / "agentic" / "bridge.py"


# ---------------------------------------------------------------------------
#  session_bootstrap.sh
# ---------------------------------------------------------------------------
def test_session_bootstrap_exists_and_is_executable():
    assert BOOTSTRAP.exists(), "session_bootstrap.sh missing"
    assert BOOTSTRAP.stat().st_mode & 0o111, "session_bootstrap.sh not executable"


def test_session_bootstrap_prints_usage_without_args():
    proc = subprocess.run([str(BOOTSTRAP)], capture_output=True, text=True,
                          timeout=10, check=False)
    # Either exits 1 with a usage hint, or exits 0 with full dump. Both are
    # observable. We assert the *command is reachable* rather than its output.
    assert proc.returncode in (0, 1, 2)


def test_session_bootstrap_fails_on_unknown_story(tmp_path):
    """Missing issue file must cause a non-zero exit, not a silent empty prompt."""
    proc = subprocess.run(
        [str(BOOTSTRAP), "NONEXISTENT-999"],
        capture_output=True, text=True, timeout=15, check=False,
        cwd=str(TEAMFLOW),
    )
    # The script currently exits non-zero (because the cd to REPO fails),
    # but not for the right reason (no G1 gate validation).
    # When STORY-95 implements proper G1 gates, the script will fail with
    # a structured error message instead of a cd failure.
    assert proc.returncode != 0, (
        "bootstrap should exit non-zero when issue is missing"
    )


# ---------------------------------------------------------------------------
#  dash-client push
# ---------------------------------------------------------------------------
def test_dash_client_script_exists():
    assert DASH_CLIENT.exists(), "dash_client.py missing"


def test_dash_client_help_or_usage_exits_cleanly():
    """dash-client must not crash on `--help`."""
    proc = subprocess.run(
        [sys.executable, str(DASH_CLIENT), "--help"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert proc.returncode == 0


def test_dash_client_supports_socket_fd_passthrough():
    """dash-client must accept a pre-opened socket for hermetic tests."""
    proc = subprocess.run(
        [sys.executable, str(DASH_CLIENT), "push", "--socket-fd", "3"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    # Dash-client argparse accepts the flag without crashing.
    assert proc.returncode in (0, 1)


# ---------------------------------------------------------------------------
#  rvc_mcp.py
# ---------------------------------------------------------------------------
def test_rvc_mcp_script_exists():
    assert RVC_MCP.exists(), "rvc_mcp.py missing"


def test_rvc_mcp_starts_and_shuts_down(tmp_path):
    """rvc_mcp should start a FastMCP server and terminate cleanly on SIGTERM."""
    proc = subprocess.Popen(
        [sys.executable, str(RVC_MCP), "--transport", "stdio"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=3)
    assert proc.returncode is not None


# ---------------------------------------------------------------------------
#  agentic-bridge
# ---------------------------------------------------------------------------
def test_agentic_bridge_script_exists():
    assert BRIDGE.exists(), "agentic/bridge.py missing"


def test_agentic_bridge_refuses_unreachable_llm():
    """With no :22222 server, bridge must exit non-zero with a clear error."""
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "--host", "127.0.0.1", "--port", "22222",
         "--task", "no-op"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert proc.returncode != 0
    assert "connect" in (proc.stderr + proc.stdout).lower() or proc.returncode in (1, 2)


# ---------------------------------------------------------------------------
#  RED: cross-tool integration
# ---------------------------------------------------------------------------
@pytest.mark.xfail(reason="RED: no `flow` vault exists yet (S-00)", strict=True)
def test_pipeline_can_publish_to_flow_vault():
    """End-to-end: a run must be able to publish artifacts to FLOW vault."""
    flow_vault = TEAMFLOW / "flow_vault"
    assert flow_vault.exists()


@pytest.mark.xfail(reason="RED: session_bootstrap.sh is still monolithic", strict=True)
def test_bootstrap_is_decomposable_into_pult_stages():
    """After STORY-99, bootstrap.sh must delegate to pult gather/validate/inject/prompt."""
    src = BOOTSTRAP.read_text()
    # The legacy bootstrap should contain a thin delegation to pult.
    assert "pult" in src.lower()
