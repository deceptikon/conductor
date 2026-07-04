"""Pult staged subcommands — `pult gather / validate / inject / prompt / publish`.

MAP.md stages 1a–1d and 11 correspond to these four subcommands plus
artifact publishing. Pult itself does not yet exist (STORY-95/96/99);
these tests pin the contract so each stage is independently testable.

All tests are RED until pult is built.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.xfail(
    reason="RED: conductor.pult module does not exist yet (STORY-95/96/99)",
    strict=True,
)


def _import_pult():
    try:
        from conductor import pult  # type: ignore
        return pult
    except ImportError:
        pytest.fail("RED: `conductor.pult` module does not exist yet (STORY-95).")


# ---------------------------------------------------------------------------
#  STAGE 1a: pult gather
# ---------------------------------------------------------------------------
def test_pult_gather_collects_git_state(tmp_git_repo):
    pult = _import_pult()
    bundle = pult.gather(tmp_git_repo, issue_id=None)
    assert "git_branch" in bundle
    assert "git_recent_commits" in bundle


def test_pult_gather_includes_state_json_when_present(tmp_git_repo):
    pult = _import_pult()
    (tmp_git_repo / "STATE.json").write_text('{"last_active": "STORY-01"}')
    bundle = pult.gather(tmp_git_repo, issue_id=None)
    assert bundle["state_json"]["last_active"] == "STORY-01"


def test_pult_gather_includes_decisions_and_gotchas(tmp_git_repo):
    pult = _import_pult()
    (tmp_git_repo / "DECISIONS.md").write_text("- Decision 1\n- Decision 2\n")
    (tmp_git_repo / "GOTCHAS.md").write_text("- Gotcha A\n")
    bundle = pult.gather(tmp_git_repo, issue_id=None)
    assert len(bundle["decisions"]) >= 1
    assert len(bundle["gotchas"]) >= 1


def test_pult_gather_returns_json_serializable_dict(tmp_git_repo):
    pult = _import_pult()
    bundle = pult.gather(tmp_git_repo, issue_id=None)
    # Must be JSON-dumpable so downstream stages can persist/emit it.
    json.dumps(bundle)


# ---------------------------------------------------------------------------
#  STAGE 1b: pult validate
# ---------------------------------------------------------------------------
def test_pult_validate_g1_issue_file_exists(tmp_path):
    pult = _import_pult()
    with pytest.raises(Exception):  # GateError once pult lands
        pult.validate(tmp_path, phase="SYNC", issue_file=tmp_path / "MISSING.md")


def test_pult_validate_g2_5_rvc_reachable():
    pult = _import_pult()
    # With no real RVC binary available, this must raise a structured error.
    with pytest.raises(Exception):
        pult.validate(Path("/tmp"), phase="SYNC", rvc_binary="/nonexistent")


def test_pult_validate_g3_predecessor_artifacts(tmp_path):
    pult = _import_pult()
    # ENGAGE without a ready SYNC artifact must raise.
    with pytest.raises(Exception):
        pult.validate(tmp_path, phase="ENGAGE")


# ---------------------------------------------------------------------------
#  STAGE 1c: pult inject
# ---------------------------------------------------------------------------
def test_pult_inject_sync_autogenerates_artifacts(tmp_path, tmp_vault):
    pult = _import_pult()
    paths = pult.inject(tmp_vault, phase="SYNC", story_id="STORY-01",
                        output_dir=tmp_path)
    assert "sync_artifact" in paths
    assert Path(paths["sync_artifact"]).exists()


def test_pult_inject_engage_only_creates_blanks(tmp_path, tmp_vault):
    pult = _import_pult()
    paths = pult.inject(tmp_vault, phase="ENGAGE", story_id="STORY-01",
                        output_dir=tmp_path)
    for expected in ("engage_artifact",):
        # ENGAGE artifacts start empty — ACT/WRAP content is written by the worker.
        assert Path(paths[expected]).exists()
        assert Path(paths[expected]).stat().st_size == 0


def test_pult_inject_is_idempotent(tmp_path, tmp_vault):
    """Two consecutive injections produce the same filenames and contents."""
    pult = _import_pult()
    a = pult.inject(tmp_vault, phase="SYNC", story_id="STORY-01",
                    output_dir=tmp_path)
    b = pult.inject(tmp_vault, phase="SYNC", story_id="STORY-01",
                    output_dir=tmp_path)
    assert a == b


# ---------------------------------------------------------------------------
#  STAGE 1d: pult prompt
# ---------------------------------------------------------------------------
def test_pult_prompt_emits_hard_stop_first(tmp_path, tmp_vault):
    pult = _import_pult()
    prompt = pult.prompt(tmp_vault, phase="ACT", story_id="STORY-01")
    assert "HARD STOP" in prompt.upper()
    # The HARD STOP block must appear before the context payload.
    hs_pos = prompt.upper().find("HARD STOP")
    ctx_pos = prompt.upper().find("CONTEXT")
    assert hs_pos < ctx_pos


def test_pult_prompt_phase_specific(tmp_path, tmp_vault):
    pult = _import_pult()
    sync_prompt = pult.prompt(tmp_vault, phase="SYNC", story_id="STORY-01")
    act_prompt = pult.prompt(tmp_vault, phase="ACT", story_id="STORY-01")
    assert sync_prompt != act_prompt


def test_pult_prompt_wraps_code_in_phase_marker():
    """WRAP phase prompt must explicitly prohibit code mutation."""
    pult = _import_pult()
    # Need a vault with a story so WRAP has something to wrap
    pytest.skip("Requires vault with prior-phase artifacts — STORY-96 contract")


# ---------------------------------------------------------------------------
#  STAGE 11: pult publish (artifact publishing to FLOW vault)
# ---------------------------------------------------------------------------
def test_pult_publish_resolves_cross_vault_links(tmp_path, tmp_vault):
    pult = _import_pult()
    flow_vault = tmp_path / "flow"
    flow_vault.mkdir()
    artifacts = pult.publish(
        source_vault=tmp_vault, flow_vault=flow_vault,
        story_id="STORY-01", artifacts={"sync": "x"},
    )
    # Contract: every [[LINK]] in synced artifacts must resolve in the
    # flow vault after publish.
    assert len(artifacts) == 1


def test_pult_publish_fails_if_flow_vault_unreachable():
    pult = _import_pult()
    with pytest.raises(Exception):
        pult.publish(
            source_vault=Path("/tmp/src"),
            flow_vault=Path("/definitely/not/a/vault"),
            story_id="STORY-01", artifacts={},
        )
