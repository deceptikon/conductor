"""Worker extraction utilities + registry.

Tests `conductor.workers.base` which already exists: ANSI stripping,
`extract_stream_json()`, and the `WorkerRegistry` API.

These tests should be GREEN — if RED, the underlying code has regressed.
"""
from __future__ import annotations

import json

import pytest

from conductor.workers.base import (
    WorkerRegistry,
    WorkerResult,
    _strip_ansi,
    extract_stream_json,
)


# ---------------------------------------------------------------------------
#  ANSI stripping
# ---------------------------------------------------------------------------
def test_strip_ansi_no_codes():
    assert _strip_ansi("plain text") == "plain text"


def test_strip_ansi_fg_bold_reset():
    assert _strip_ansi("\x1b[1;32mSUCCESS\x1b[0m") == "SUCCESS"


def test_strip_ansi_cursor_movement():
    assert _strip_ansi("\x1b[2J\x1b[Hcleared") == "cleared"


def test_strip_ansi_empty_string():
    assert _strip_ansi("") == ""


# ---------------------------------------------------------------------------
#  extract_stream_json() — core worker-output parser
# ---------------------------------------------------------------------------
def test_extract_text_blocks_from_message_content():
    stdout = (
        "\n".join([
            json.dumps({"message": {"content": [{"type": "text", "text": "hello"}]}}),
            json.dumps({"message": {"content": [{"type": "text", "text": " world"}]}}),
        ])
    )
    assert extract_stream_json(stdout) == "hello\n world"


def test_extract_prefers_result_field_when_present():
    stdout = "\n".join([
        json.dumps({"message": {"content": [{"type": "text", "text": "ignored"}]}}),
        json.dumps({"type": "result", "result": "FINAL ANSWER"}),
    ])
    assert extract_stream_json(stdout) == "FINAL ANSWER"


def test_extract_malformed_lines_dropped_gracefully():
    stdout = "not-json-line\n{bad-json\n" + json.dumps({"message": {"content": [{"type": "text", "text": "ok"}]}})
    assert extract_stream_json(stdout) == "ok"


def test_extract_return_dropped_flag():
    stdout = "garbage\n" + json.dumps({"message": {"content": [{"type": "text", "text": "ok"}]}})
    text, dropped = extract_stream_json(stdout, return_dropped=True)
    assert text == "ok"
    assert dropped == ["garbage"]


def test_extract_empty_content_block_falls_back_to_raw():
    """When `content` blocks present but all empty, stdout is returned."""
    stdout = json.dumps({"message": {"content": [{"type": "text", "text": ""}]}})
    assert extract_stream_json(stdout) == stdout


def test_extract_non_json_falls_through_to_raw():
    """If no JSON is parseable, the whole stdout is returned as text (stripped)."""
    raw = "totally\nplain\noutput\n"
    assert extract_stream_json(raw) == raw.strip()


# ---------------------------------------------------------------------------
#  WorkerResult dataclass
# ---------------------------------------------------------------------------
def test_worker_result_fields():
    r = WorkerResult(
        worker="claude", ok=True, text="hi", raw="raw hi",
        returncode=0, cmd="claude --prompt hi",
    )
    assert r.worker == "claude"
    assert r.ok is True
    assert r.error == ""


# ---------------------------------------------------------------------------
#  WorkerRegistry API
# ---------------------------------------------------------------------------
class _StubBackend:
    name = "stub"
    def build_cmd(self, *a, **k): return []
    def extract_text(self, s): return s


def test_registry_register_and_get():
    reg = WorkerRegistry()
    b = _StubBackend()
    reg.register(b)
    assert reg.get("stub") is b


def test_registry_get_missing_raises_keyerror():
    reg = WorkerRegistry()
    with pytest.raises(KeyError, match="unknown worker 'nope'"):
        reg.get("nope")


def test_registry_has_and_names():
    reg = WorkerRegistry()
    assert reg.has("stub") is False
    reg.register(_StubBackend())
    assert reg.has("stub") is True
    assert reg.names() == ["stub"]


def test_registry_overwrites_duplicate():
    reg = WorkerRegistry()
    b1 = _StubBackend()
    b2 = _StubBackend()
    reg.register(b1); reg.register(b2)
    assert reg.get("stub") is b2
