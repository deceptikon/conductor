"""G1–G6 boundary gates — the core of the TDD plan (P0.0.0).

These tests pin the contract of **every gate** from ASSEMBLY.md §G1–G6.
The gate *logic* does not exist yet — the functions these tests call
will be introduced as STORY-94 (paths.py / G5), STORY-95 (G2/G2.5),
STORY-96 (G3), STORY-97 (G1), and STORY-101 (G6) land.

All tests are RED until the implementation arrives.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.xfail(
    reason="RED: conductor.gates module does not exist yet (STORY-94/95/96/97)",
    strict=True,
)


# ---------------------------------------------------------------------------
#  Import the *target* module surfaces. They don't exist yet — the test
#  runner will fail on ImportError, which pytest counts as a failure.
#  We wrap in pytest.raises so the *assertion* is "this import failed"
#  during RED, and flips to a real import during GREEN.
# ---------------------------------------------------------------------------
def _import_gates():
    try:
        from conductor import gates  # type: ignore
        return gates
    except ImportError:
        pytest.fail(
            "RED: `conductor.gates` module does not exist yet. "
            "Implement G1–G6 gate helpers (see STORY-010 / ASSEMBLY.md)."
        )


# ---------------------------------------------------------------------------
#  G1 — Issue pre-check
# ---------------------------------------------------------------------------
def test_g1_issue_precheck_rejects_missing_file(tmp_path):
    gates = _import_gates()
    with pytest.raises(gates.GateError, match="G1"):
        gates.check_issue_file(tmp_path / "MISSING.md")


def test_g1_issue_precheck_accepts_valid_file(tmp_vault_with_story):
    gates = _import_gates()
    vault, story = tmp_vault_with_story
    gates.check_issue_file(story)  # must NOT raise


def test_g1_issue_precheck_rejects_malformed_frontmatter(tmp_path):
    bad = tmp_path / "STORY-99.md"
    bad.write_text("no frontmatter here")
    gates = _import_gates()
    with pytest.raises(gates.GateError, match="frontmatter"):
        gates.check_issue_file(bad)


# ---------------------------------------------------------------------------
#  G2 — Bootstrap payload validation
# ---------------------------------------------------------------------------
def test_g2_payload_missing_issue_section():
    gates = _import_gates()
    with pytest.raises(gates.GateError, match="G2"):
        gates.validate_bootstrap_payload({"CONTEXT": "x", "INSTRUCTIONS": "y"})


def test_g2_payload_missing_context_section():
    gates = _import_gates()
    with pytest.raises(gates.GateError):
        gates.validate_bootstrap_payload({"ISSUE": "x", "INSTRUCTIONS": "y"})


def test_g2_payload_complete_passes():
    gates = _import_gates()
    gates.validate_bootstrap_payload({
        "ISSUE": "STORY-01", "CONTEXT": "body", "INSTRUCTIONS": "do x",
    })


# ---------------------------------------------------------------------------
#  G2.5 — RVC reachability
# ---------------------------------------------------------------------------
def test_g2_5_rvc_reachable_success():
    gates = _import_gates()
    # `/bin/true` is the stand-in for a reachable binary.
    gates.check_rvc_reachable(binary="/bin/true", timeout=2)


def test_g2_5_rvc_unreachable_raises_gate_error():
    gates = _import_gates()
    with pytest.raises(gates.GateError, match="RVC"):
        gates.check_rvc_reachable(binary="/nonexistent/binary", timeout=0.1)


# ---------------------------------------------------------------------------
#  G3 — Phase artifact gate
# ---------------------------------------------------------------------------
def test_g3_artifact_gate_blocks_when_predecessor_missing(tmp_path):
    gates = _import_gates()
    with pytest.raises(gates.GateError, match="G3"):
        gates.check_phase_artifact(tmp_path, phase="ENGAGE")


def test_g3_artifact_gate_passes_when_predecessor_ready(tmp_path):
    gates = _import_gates()
    artifact = tmp_path / "SYNC.artifact.json"
    artifact.write_text('{"status": "ready"}')
    gates.check_phase_artifact(tmp_path, phase="ENGAGE")  # should not raise


# ---------------------------------------------------------------------------
#  G4 — QA gate (before commit)
# ---------------------------------------------------------------------------
def test_g4_qa_gate_blocks_commit_when_tests_failed():
    gates = _import_gates()
    with pytest.raises(gates.GateError, match="G4"):
        gates.check_qa_passed(qa_passed=False, qa_attempts=3)


def test_g4_qa_gate_allows_commit_when_tests_passed():
    gates = _import_gates()
    gates.check_qa_passed(qa_passed=True, qa_attempts=1)  # ok


# ---------------------------------------------------------------------------
#  G5 — Path resolution via pyproject.toml crawl
# ---------------------------------------------------------------------------
def test_g5_path_resolution_crawls_to_pyproject(tmp_path):
    gates = _import_gates()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert gates.get_repo_root(nested) == tmp_path


def test_g5_path_resolution_fails_cleanly_without_pyproject(tmp_path):
    gates = _import_gates()
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    with pytest.raises(gates.PathResolutionError):
        gates.get_repo_root(isolated)


# ---------------------------------------------------------------------------
#  G6 — Canonical spec gate (STORY-101)
# ---------------------------------------------------------------------------
def test_g6_canonical_spec_gate_rejects_stale_duplicate(tmp_path):
    gates = _import_gates()
    # A spec living outside TEAMFLOW/20_Specs is NOT canonical.
    stale = tmp_path / "ADLAI" / "ASSEMBLY.md"
    stale.parent.mkdir()
    stale.write_text("# stale")
    with pytest.raises(gates.GateError, match="G6"):
        gates.check_canonical_spec(stale, canonical_root=tmp_path / "20_Specs")


def test_g6_canonical_spec_gate_accepts_canonical_copy(tmp_path):
    gates = _import_gates()
    canon_root = tmp_path / "20_Specs"
    canon_root.mkdir()
    spec = canon_root / "ASSEMBLY.md"
    spec.write_text("# canonical")
    gates.check_canonical_spec(spec, canonical_root=canon_root)


# ---------------------------------------------------------------------------
#  Cross-cutting: GateError is uniform and serializable
# ---------------------------------------------------------------------------
def test_gateerror_has_code_and_message():
    gates = _import_gates()
    err = gates.GateError("G2", "missing section")
    assert err.code == "G2"
    assert "missing section" in str(err)
