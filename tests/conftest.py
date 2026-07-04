"""Shared fixtures for conductor + pipeline test suite.

Organized so every pipeline stage can be driven in isolation — the same
shape of context that the dream-flow dry-run sample produces.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo roots — resolved once, used by every test that reaches outside the
# conductor package.
# ---------------------------------------------------------------------------
CONDUCTOR_ROOT = Path(__file__).resolve().parents[1]
TEAMFLOW_ROOT = CONDUCTOR_ROOT.parent
RVC_ROOT = TEAMFLOW_ROOT / "RVC"
DASH_ROOT = TEAMFLOW_ROOT / "dash"
WORKSPACE_ROOT = TEAMFLOW_ROOT.parent  # ~/X

RVC_CLI = RVC_ROOT / "rvc-cli.py"
BOOTSTRAP_SH = TEAMFLOW_ROOT / "00_Project" / "session_bootstrap.sh"


# ---------------------------------------------------------------------------
# Vault scaffold — a tempdir that looks like an RVC vault
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a minimal RVC vault in a temp directory.

    Layout mirrors the real ADLAI/TEAMFLOW/RVC vaults so rvc-cli logic
    (find_vault_root / find_file_by_id) works identically under test.
    """
    vault = tmp_path / "vault"
    for sub in (
        "00_Project",
        "10_Issues/01_To_Do",
        "10_Issues/02_Active",
        "10_Issues/03_Review",
        "10_Issues/04_Done",
        "20_Specs",
        "90_Assets",
        "99_Archive",
        ".obsidian",
    ):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    (vault / ".rvc-root").write_text("# RVC vault root\n")
    return vault


@pytest.fixture
def tmp_vault_with_story(tmp_vault: Path) -> tuple[Path, Path]:
    """`tmp_vault` plus one STORY-01 issue file — the minimum for `rvc get`."""
    story = tmp_vault / "10_Issues" / "01_To_Do" / "STORY-01-Test-story.md"
    story.write_text(
        "---\n"
        "id: STORY-01\n"
        "type: story\n"
        "status: To Do\n"
        "title: Test story\n"
        "---\n"
        "# STORY-01: Test story\n\n"
        "## Context\nA test story for pipeline verification.\n\n"
        "## Acceptance Criteria\n- [ ] passes\n"
    )
    return tmp_vault, story


@pytest.fixture
def tmp_vault_with_linked_spec(tmp_vault_with_story: tuple[Path, Path]) -> tuple[Path, Path, Path]:
    """`tmp_vault_with_story` plus a linked spec the `[[...]]` resolves to."""
    vault, story = tmp_vault_with_story
    spec = vault / "20_Specs" / "TEST-SPEC.md"
    spec.write_text("---\ntype: spec\n---\n# Test Spec\nBody of the spec.\n")
    # rewrite the story body to reference [[TEST-SPEC]]
    story.write_text(
        story.read_text().replace(
            "## Context\nA test story for pipeline verification.",
            "## Context\nA test story. See [[TEST-SPEC]].",
        )
    )
    return vault, story, spec


# ---------------------------------------------------------------------------
# Git repo — for any test that needs a real .git (commit_node, rvc sync, ...)
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Initialise a throwaway git repo with a single commit on `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, env=env)
    (repo / "README").write_text("initial\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=env)
    return repo


# ---------------------------------------------------------------------------
# Fake worker — the stand-in used by every pipeline-node test
# ---------------------------------------------------------------------------
class FakeWorker:
    """A `Worker`-shaped object returning scripted text per call."""

    def __init__(self, responses: list[str] | None = None, name: str = "fake"):
        self.name = name
        self.model = "fake-model"
        self.read_only = False
        self._responses = list(responses or ['{"ok": true}'])
        self.calls: list[dict] = []

    def run(self, prompt: str, cwd: Path | None = None, timeout: int = 60) -> "FakeResult":
        self.calls.append({"prompt": prompt, "cwd": cwd, "timeout": timeout})
        text = self._responses[len(self.calls) - 1] if len(self.calls) <= len(self._responses) else self._responses[-1]
        return FakeResult(text=text)


class FakeResult:
    def __init__(self, text: str, ok: bool = True, returncode: int = 0, raw: str = ""):
        self.worker = "fake"
        self.ok = ok
        self.text = text
        self.raw = raw or text
        self.returncode = returncode
        self.cmd = "fake-cmd"
        self.error = ""


@pytest.fixture
def fake_worker():
    """Single-call fake worker returning a valid plan JSON."""
    plan = {
        "id": "plan-1",
        "version": 1,
        "nodes": [
            {
                "id": "n1",
                "description": "do something",
                "dependencies": [],
                "expected_output": "a file",
                "test_case": "file exists",
                "artifact_path": "out.txt",
            }
        ],
        "topo_order": ["n1"],
    }
    return FakeWorker([json.dumps(plan)])


@pytest.fixture
def fake_qa_pass(tmp_path: Path):
    """A QA command that always succeeds (exit 0)."""
    script = tmp_path / "qa_pass.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def fake_qa_fail(tmp_path: Path):
    """A QA command that always fails (exit 1) with a useful stderr."""
    script = tmp_path / "qa_fail.sh"
    script.write_text("#!/bin/sh\necho 'FAIL: missing import' >&2\nexit 1\n")
    script.chmod(0o755)
    return str(script)
