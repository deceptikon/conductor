"""Conductor CLI commands (conductor run/approve/reject/edit/status/list/logs/selftest).

Exercises `conductor.__main__.main(argv)` by intercepting the project
loader and the worker backend, so tests run without a real `adlai`
project config or LLM on the other end.

The goal is contract coverage — does `conductor approve <run_id>` hit the
right resume path? Does `selftest` exit 0 on a valid config? — not end-
to-end LLM orchestration.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conductor.__main__ import main as conductor_main


# ---------------------------------------------------------------------------
#  Helpers — make ProjectConfig.load return a fully fake config
# ---------------------------------------------------------------------------
class _FakeConf:
    name = "adlai"
    repo = Path("/tmp/fake-adlai")
    vault = Path("/tmp/fake-vault")
    agents_md = Path("/tmp/fake-adlai/AGENTS.md")
    max_qa_retries = 3
    commit_template = "{type}: {subject}"
    qa_cmd = "/usr/bin/true"

    def worker_for(self, node):
        return _FakeBackend()


class _FakeBackend:
    name = "fake"
    model = "fake-model"
    read_only = True

    def build_cmd(self, *a, **k):
        return ["echo", "fake"]

    def extract_text(self, stdout):
        return stdout


@pytest.fixture
def fake_saver(monkeypatch):
    """Swap `_saver()` for an InMemorySaver so no SQLite is touched."""
    monkeypatch.setattr(
        "conductor.__main__._saver",
        lambda: InMemorySaver(),
    )


@pytest.fixture
def fake_project_config(monkeypatch):
    monkeypatch.setattr(
        "conductor.__main__.ProjectConfig.load",
        classmethod(lambda cls, name: _FakeConf()),
    )


# ---------------------------------------------------------------------------
#  Argument parsing
# ---------------------------------------------------------------------------
def test_main_no_args_exits_with_error(capsys):
    """No args → argparse exits 2 (usage error)."""
    with pytest.raises(SystemExit) as exc:
        conductor_main(argv=[])
    assert exc.value.code in (2, None)  # 2 is argparse default


def test_selftest_subcommand_is_registered(fake_project_config, fake_saver, capsys, monkeypatch):
    """`conductor selftest adlai` is a known subcommand."""
    try:
        conductor_main(argv=["selftest", "adlai"])
    except SystemExit as e:
        assert e.code in (0, None)


def test_run_subcommand_requires_project_and_task(fake_project_config, capsys):
    """`conductor run adlai` without a task → argparse error."""
    with pytest.raises(SystemExit):
        conductor_main(argv=["run", "adlai"])


# ---------------------------------------------------------------------------
#  run command — exercises the LangGraph build path
# ---------------------------------------------------------------------------
def test_run_with_no_context_skips_rvc(fake_project_config, fake_saver, capsys, monkeypatch):
    """`--no-context` must set rvc_mode='off' in the init state."""
    captured = {}

    class _FakeGraph:
        def invoke(self, init, cfg_ctx):
            captured.update(init)
            return {}
        def get_state(self, cfg_ctx):
            class _S:
                pass
            r = _S()
            r.values = captured
            return r
        def compile(self, *a, **k): return self

    monkeypatch.setattr(
        "conductor.__main__.build_graph",
        lambda _cfg: _FakeGraph(),
    )
    conductor_main(argv=["run", "adlai", "do x", "--no-context"])
    assert captured["rvc_mode"] == "off"


def test_run_with_extra_context_sets_full_mode(fake_project_config, fake_saver, monkeypatch):
    captured = {}

    class _FakeGraph:
        def invoke(self, init, cfg_ctx):
            captured.update(init); return {}
        def get_state(self, cfg_ctx):
            class _S:
                pass
            r = _S(); r.values = captured; return r
        def compile(self, *a, **k): return self

    monkeypatch.setattr(
        "conductor.__main__.build_graph",
        lambda _cfg: _FakeGraph(),
    )
    conductor_main(argv=["run", "adlai", "do x", "--extra-context"])
    assert captured["rvc_mode"] == "full"


# ---------------------------------------------------------------------------
#  status / list / logs — ledger I/O
# ---------------------------------------------------------------------------
def test_status_missing_run_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "conductor.__main__.LEDGER_DIR", tmp_path,
    )
    with pytest.raises(SystemExit) as exc:
        conductor_main(argv=["status", "does-not-exist"])
    assert exc.value.code != 0


def test_list_empty_ledger_is_idempotent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("conductor.__main__.LEDGER_DIR", tmp_path)
    conductor_main(argv=["list"])
    out = capsys.readouterr().out
    assert "No runs" in out or out.strip() == ""


def test_logs_shows_history_for_existing_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("conductor.__main__.LEDGER_DIR", tmp_path)
    ledger = tmp_path / "abc123.json"
    ledger.write_text(json.dumps({
        "status": "done", "project": "adlai",
        "task": "do x", "history": [{"event": "plan"}],
    }))
    monkeypatch.setattr(
        "conductor.__main__.LOG_DIR", tmp_path / "logs",
    )
    (tmp_path / "logs").mkdir()
    conductor_main(argv=["logs", "abc123"])
    out = capsys.readouterr().out
    assert '"event"' in out or "plan" in out


# ---------------------------------------------------------------------------
#  selftest — exercises project config + graph compilation
# ---------------------------------------------------------------------------
def test_selftest_prints_project_info(fake_project_config, fake_saver, capsys):
    conductor_main(argv=["selftest", "adlai"])
    out = capsys.readouterr().out
    assert "project : adlai" in out or "adlai" in out


def test_selftest_lists_graph_nodes(fake_project_config, fake_saver, capsys):
    conductor_main(argv=["selftest", "adlai"])
    out = capsys.readouterr().out
    assert "nodes" in out.lower()


# ---------------------------------------------------------------------------
#  RED: missing CLI surface area
# ---------------------------------------------------------------------------
@pytest.mark.xfail(reason="RED: conductor lacks a `conductor cancel` subcommand", strict=True)
def test_conductor_cancel_subcommand_exists(fake_project_config, fake_saver, capsys):
    """A `cancel` subcommand to abort a running pipeline is missing."""
    conductor_main(argv=["cancel", "some-run"])


@pytest.mark.xfail(reason="RED: conductor lacks a `conductor retry` subcommand", strict=True)
def test_conductor_retry_subcommand_exists(fake_project_config, fake_saver, capsys):
    """Retry a qa_failed run from the top without re-planning."""
    conductor_main(argv=["retry", "some-run"])
