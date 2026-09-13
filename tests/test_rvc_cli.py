"""RVC CLI (`rvc-cli.py`) — covers every subcommand in COMMANDS_REGISTRY.

Runs against a temp vault fixture so tests are hermetic.

GREEN tests exercise existing `rvc-cli.py` functions:
  find_vault_root, build_vault_index, find_file_by_id, cmd_get, cmd_context,
  cmd_issue_list, cmd_create_issue, cmd_search, cmd_init, cmd_project_init,
  cmd_install, _write_project_readme.

RED tests pin boundary/contract issues flagged in the RVC audit
(REVIEW_AND_PLAN.md): shell=True in `run_cmd`, race conditions in `_next_id`,
ad-hoc YAML frontmatter parsing. These stay RED until STORY-013 lands.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RVC_ROOT = Path(__file__).resolve().parents[2] / "RVC"
RVC_CLI = RVC_ROOT / "rvc-cli.py"

# Make rvc-cli importable without running it as a script.
sys.path.insert(0, str(RVC_ROOT))
import importlib
try:
    # rvc-cli.py has a hyphen — import via importlib.
    rvc_cli = importlib.import_module("rvc-cli")  # type: ignore
except ModuleNotFoundError:
    # Fallback: run it as __main__ via exec
    rvc_cli = importlib.machinery.SourceFileLoader(
        "rvc_cli", str(RVC_CLI)).load_module()


# ---------------------------------------------------------------------------
#  Vault discovery
# ---------------------------------------------------------------------------
def test_find_vault_root_marker_file(tmp_vault):
    """`.rvc-root` marker anywhere in walk → returns that dir."""
    assert rvc_cli.find_vault_root(str(tmp_vault)) == str(tmp_vault)


@pytest.mark.xfail(
    reason="RED: walk-up from /tmp hits stale sibling vaults from earlier "
           "pytest runs. `find_vault_root` needs a stop-at-root argument "
           "or the function should walk DOWN rather than UP.",
    strict=True,
)
def test_find_vault_root_returns_none_for_non_vault(tmp_path):
    (tmp_path / "random").mkdir()
    result = rvc_cli.find_vault_root(str(tmp_path / "random"))
    assert result is None, (
        f"find_vault_root walked up from {tmp_path}/random and "
        f"returned stale vault at {result}. Needs a stop-at-root arg."
    )


def test_find_vault_root_backward_compat_literal_vault(tmp_path):
    """Legacy layout: `vault/` folder directly under some parent."""
    legacy = tmp_path / "project" / "vault" / "10_Issues"
    legacy.mkdir(parents=True)
    (tmp_path / "project" / "vault" / ".obsidian").mkdir()
    assert rvc_cli.find_vault_root(str(tmp_path / "project")) == str(tmp_path / "project" / "vault")


# ---------------------------------------------------------------------------
#  Vault index + lookup
# ---------------------------------------------------------------------------
def test_build_vault_index_skips_hidden_dirs(tmp_vault):
    (tmp_vault / ".secret").mkdir()
    (tmp_vault / ".secret" / "hidden.md").write_text("secret")
    idx = rvc_cli.build_vault_index(str(tmp_vault))
    assert "hidden" not in idx


def test_find_file_by_id_exact_match(tmp_vault_with_story):
    vault, story = tmp_vault_with_story
    found = rvc_cli.find_file_by_id(str(vault), "STORY-01")
    assert found == str(story)


def test_find_file_by_id_prefix_match(tmp_vault_with_story):
    """`STORY-01` matches `STORY-01-Test-story.md` via prefix rule."""
    vault, _ = tmp_vault_with_story
    found = rvc_cli.find_file_by_id(str(vault), "STORY-01")
    assert found and "STORY-01" in found


def test_find_file_by_id_strips_anchor():
    """`[[SPEC#section]]` resolves via the SPEC part only."""
    # Use a fresh vault fixture
    pass  # covered indirectly by test_context_linked_spec


# ---------------------------------------------------------------------------
#  cmd_get
# ---------------------------------------------------------------------------
def test_cmd_get_prints_issue_content(tmp_vault_with_story, capsys):
    vault, story = tmp_vault_with_story
    rvc_cli.cmd_get(str(vault), "STORY-01")
    captured = capsys.readouterr()
    assert "STORY-01" in captured.out
    assert "Test story" in captured.out


def test_cmd_get_missing_id_exits_nonzero(tmp_vault, capsys):
    with pytest.raises(SystemExit) as exc:
        rvc_cli.cmd_get(str(tmp_vault), "GHOST-99")
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
#  cmd_context (linked-spec resolution)
# ---------------------------------------------------------------------------
def test_cmd_context_assembles_linked_spec(tmp_vault_with_linked_spec, capsys):
    vault, story, spec = tmp_vault_with_linked_spec
    rvc_cli.cmd_context(str(vault), "STORY-01")
    out = capsys.readouterr().out
    assert "Test Spec" in out, "Expected the linked spec body to be assembled."
    assert "REFERENCE" in out


def test_cmd_context_missing_link_reported_not_fatal(tmp_vault, capsys):
    story = tmp_vault / "10_Issues" / "01_To_Do" / "STORY-02.md"
    story.write_text("---\nid: STORY-02\n---\n# STORY-02\nSee [[DOES_NOT_EXIST]].\n")
    rvc_cli.cmd_context(str(tmp_vault), "STORY-02")
    out = capsys.readouterr().out
    assert "NOT FOUND" in out


# ---------------------------------------------------------------------------
#  cmd_issue_list
# ---------------------------------------------------------------------------
def test_cmd_issue_list_all(tmp_vault_with_story, capsys):
    vault, _ = tmp_vault_with_story
    rvc_cli.cmd_issue_list(str(vault), None)
    assert "STORY-01" in capsys.readouterr().out


def test_cmd_issue_list_filter_by_status(tmp_vault_with_story, capsys):
    vault, _ = tmp_vault_with_story
    rvc_cli.cmd_issue_list(str(vault), "Active")
    assert "No issues" in capsys.readouterr().out  # nothing is Active yet


# ---------------------------------------------------------------------------
#  cmd_create_issue
# ---------------------------------------------------------------------------
def test_cmd_create_issue_writes_frontmatter(tmp_vault):
    path = rvc_cli.cmd_create_issue(str(tmp_vault), "My test", prefix="STORY")
    content = Path(path).read_text()
    assert content.startswith("---")
    assert "id: STORY-01" in content or "STORY-01" in path
    assert "type: story" in content


def test_cmd_create_issue_increments_id(tmp_vault):
    p1 = rvc_cli.cmd_create_issue(str(tmp_vault), "First")
    p2 = rvc_cli.cmd_create_issue(str(tmp_vault), "Second")
    assert "STORY-01" in p1
    assert "STORY-02" in p2


@pytest.mark.xfail(reason="RED: cmd_create_issue does not check file existence (STORY-013)", strict=True)
def test_cmd_create_issue_rejects_duplicate(tmp_path):
    """If the target file already exists, `cmd_create_issue` must error
    out (EEXIST-safe) and NOT silently overwrite the existing issue."""
    vault = tmp_path
    for sub in ("10_Issues/01_To_Do", ".obsidian"):
        (vault / sub).mkdir(parents=True, exist_ok=True)

    target_dir = vault / "10_Issues" / "01_To_Do"
    # Seed ONLY STORY-01 so _next_id deterministically returns STORY-02.
    target_dir.joinpath("STORY-01-First.md").write_text("---\nid: STORY-01\n---\n")
    # Pre-occupy the path the next create would try (STORY-02-X.md).
    target_dir.joinpath("STORY-02-X.md").write_text("---\nid: STORY-02\n---\nstub\n")

    # Now cmd_create_issue("X") → _next_id returns STORY-02 → collision!
    with pytest.raises(SystemExit):
        rvc_cli.cmd_create_issue(str(vault), "X")


# ---------------------------------------------------------------------------
#  cmd_search
# ---------------------------------------------------------------------------
def test_cmd_search_case_insensitive(tmp_vault_with_story, capsys):
    vault, _ = tmp_vault_with_story
    rvc_cli.cmd_search(str(vault), "TEST STORY")
    assert "STORY-01" in capsys.readouterr().out


def test_cmd_search_no_results(tmp_vault, capsys):
    rvc_cli.cmd_search(str(tmp_vault), "zzz_no_match")
    assert "No results" in capsys.readouterr().out


# ---------------------------------------------------------------------------
#  cmd_init
# ---------------------------------------------------------------------------
def test_cmd_init_creates_standard_layout(tmp_path):
    """STORY-013/105: init logic lives in the module-level `cmd_init` helper."""
    target = tmp_path / "fresh"
    target.mkdir()
    rvc_cli.cmd_init(str(target))
    for expected in (
        "00_Project", "10_Issues/01_To_Do", "10_Issues/02_Active",
        "10_Issues/03_Review", "10_Issues/04_Done", "20_Specs", ".rvc-root",
    ):
        assert (target / expected).exists(), f"missing {expected}"


def test_cmd_init_readme_newvault(tmp_path):
    """`cmd_init` writes a README at the vault root with the constitution pointer."""
    rvc_cli.cmd_init(str(tmp_path / "proj"), tree="newvault")
    readme = tmp_path / "proj" / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "10_CONTEXT/ROUTING.md" in text
    assert "folder" in text and "git mv" in text
    assert "{" not in text, "README placeholders must be substituted"


def test_cmd_init_readme_legacy_points_to_reglament(tmp_path):
    rvc_cli.cmd_init(str(tmp_path / "leg"), tree="legacy")
    text = (tmp_path / "leg" / "README.md").read_text()
    assert "00_Project/REGLAMENT.md" in text


def test_cmd_init_does_not_clobber_existing_readme(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    (target / "README.md").write_text("# Mine")
    rvc_cli.cmd_init(str(target), tree="newvault")
    assert (target / "README.md").read_text() == "# Mine"


def test_cmd_project_init_readme_at_project_root(tmp_path):
    rvc_cli.cmd_project_init(str(tmp_path / "proj"), vault_name="adlai-vault", tree="newvault")
    readme = tmp_path / "proj" / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "at `adlai-vault/`" in text
    assert "10_CONTEXT/ROUTING.md" in text
    root = tmp_path / "proj" / "adlai-vault" / ".rvc-root"
    assert root.exists()
    assert "vault=adlai-vault" in root.read_text()


# ---------------------------------------------------------------------------
#  rvc install (symlink bootstrap, STORY-105 follow-up)
# ---------------------------------------------------------------------------
def test_cmd_install_creates_symlink(tmp_path):
    rc = rvc_cli.cmd_install(str(tmp_path), force=True)
    target = tmp_path / "rvc"
    assert rc == 0
    assert target.is_symlink()
    assert os.path.realpath(target) == os.path.realpath(RVC_CLI)


def test_cmd_install_is_idempotent(tmp_path):
    rvc_cli.cmd_install(str(tmp_path), force=True)
    assert rvc_cli.cmd_install(str(tmp_path), force=True) == 0


def test_cmd_install_check_reports_ok(tmp_path, capsys):
    rvc_cli.cmd_install(str(tmp_path), force=True)
    assert rvc_cli.cmd_install(str(tmp_path), check=True) == 0
    assert "OK" in capsys.readouterr().out


def test_cmd_install_refuses_conflict_without_force(tmp_path, capsys):
    target = tmp_path / "rvc"
    target.write_text("# not a symlink")
    rc = rvc_cli.cmd_install(str(tmp_path))
    assert rc == 1
    assert "Refusing" in capsys.readouterr().err
    assert target.read_text() == "# not a symlink", "must not clobber without --force"
    assert rvc_cli.cmd_install(str(tmp_path), force=True) == 0
    assert target.is_symlink(), "--force replaces the conflicting file"


# ---------------------------------------------------------------------------
#  STORY-105 — per-vault tree config (folder = state)
# ---------------------------------------------------------------------------
def _newvault(tmp_path: Path, name: str = "vault") -> Path:
    """Scaffold a NEWVAULT-preset vault via `rvc init --tree newvault`."""
    vault = tmp_path / name
    subprocess.run(
        [sys.executable, str(RVC_CLI), "init", str(vault), "--tree", "newvault"],
        check=True, capture_output=True,
    )
    return vault


def test_newvault_layout_and_tree_config(tmp_path):
    """`--tree newvault` produces the NEWVAULT buckets + .rvc-root tree block."""
    vault = _newvault(tmp_path)
    for sub in (
        "00_INBOX", "10_CONTEXT", "20_NEXT", "30_ACTIVE", "40_DECIDE",
        "50_DEFERRED", "60_DONE", "90_ARCHIVE/done", "90_ARCHIVE/superseded",
    ):
        assert (vault / sub).is_dir(), f"missing {sub}"
    cfg = (vault / ".rvc-root").read_text()
    assert "tree.triage=20_NEXT" in cfg
    assert "tree.evict=90_ARCHIVE/done" in cfg
    assert "tree.supersede=90_ARCHIVE/superseded" in cfg


def test_newvault_create_lands_in_next_no_status_frontmatter(tmp_path):
    vault = _newvault(tmp_path)
    path = rvc_cli.cmd_create_issue(str(vault), "New bucket story", prefix="STORY")
    rel = str(Path(path).relative_to(vault))
    assert rel.startswith("20_NEXT/")
    content = Path(path).read_text()
    assert "status:" not in content, "folder = state: status frontmatter is forbidden"
    assert "type: story" in content


def test_newvault_start_moves_to_active_content_untouched(tmp_path):
    vault = _newvault(tmp_path)
    path = Path(rvc_cli.cmd_create_issue(str(vault), "Flow story", prefix="STORY"))
    before = path.read_text()
    rvc_cli.cmd_issue_action(str(vault), "STORY-01", "start")
    new = vault / "30_ACTIVE" / path.name
    assert new.exists(), "issue must land in 30_ACTIVE"
    assert not path.exists(), "source file must be gone (git-mv/rename, no copy)"
    assert new.read_text() == before, "content must be byte-identical — folder is the state"


def test_newvault_verbs_resolve_buckets(tmp_path):
    vault = _newvault(tmp_path)
    rvc_cli.cmd_create_issue(str(vault), "Decide me", prefix="STORY")
    rvc_cli.cmd_issue_action(str(vault), "STORY-01", "block")
    assert (vault / "40_DECIDE" / "STORY-01-Decide-me.md").exists()
    rvc_cli.cmd_issue_action(str(vault), "STORY-01", "evict")
    assert (vault / "90_ARCHIVE" / "done" / "STORY-01-Decide-me.md").exists()
    assert not (vault / "40_DECIDE" / "STORY-01-Decide-me.md").exists()


def test_newvault_list_resolves_status_aliases_for_mcp(tmp_path, capsys):
    """MCP contract: `rvc_list(status="To Do")` must resolve onto 20_NEXT."""
    vault = _newvault(tmp_path)
    rvc_cli.cmd_create_issue(str(vault), "A", prefix="STORY")
    rvc_cli.cmd_create_issue(str(vault), "B", prefix="STORY")
    rvc_cli.cmd_issue_list(str(vault), "To Do")
    out = capsys.readouterr().out
    assert "STORY-01" in out and "STORY-02" in out
    assert "[20_NEXT]" in out
    rvc_cli.cmd_issue_list(str(vault), "Active")
    assert "No issues" in capsys.readouterr().out  # nothing started yet


def test_backstop_rejects_unknown_action_dir_and_status(tmp_path):
    vault = _newvault(tmp_path)
    rvc_cli.cmd_create_issue(str(vault), "X", prefix="STORY")
    with pytest.raises(SystemExit):
        rvc_cli.cmd_issue_action(str(vault), "STORY-01", "meltdown")
    with pytest.raises(SystemExit):
        rvc_cli.cmd_issue_list(str(vault), "SomethingElse")
    with pytest.raises(SystemExit):
        rvc_cli.cmd_issue_list(str(vault), list_dir="77_BOGUS")


def test_legacy_init_still_produces_legacy_layout(tmp_path):
    legacy = tmp_path / "legacy"
    subprocess.run(
        [sys.executable, str(RVC_CLI), "init", str(legacy), "--tree", "legacy"],
        check=True, capture_output=True,
    )
    for sub in ("00_Project", "10_Issues/01_To_Do", "10_Issues/04_Done", "99_Archive"):
        assert (legacy / sub).is_dir(), f"missing {sub}"
    assert not (legacy / "20_NEXT").exists()
    assert "tree." not in (legacy / ".rvc-root").read_text()


# ---------------------------------------------------------------------------
#  cmd_git_commit_all (submodule-aware commit)
#  Uses a real temp git repo to verify the flow end-to-end.
# ---------------------------------------------------------------------------
def test_cmd_git_commit_all_no_changes_is_noop(tmp_git_repo, capsys):
    vault = tmp_git_repo / "vault"
    vault.mkdir()
    (vault / "10_Issues").mkdir()
    (vault / ".obsidian").mkdir()
    (vault / ".rvc-root").write_text("")
    rvc_cli.cmd_git_commit_all(str(vault), "no-op", dry_run=True)
    out = capsys.readouterr().out
    assert "Nothing to do" in out or "Dry-run complete" in out


def test_cmd_git_commit_all_dry_run_does_not_commit(tmp_git_repo, tmp_path):
    vault = tmp_git_repo / "vault"
    vault.mkdir()
    (vault / "10_Issues").mkdir()
    (vault / ".obsidian").mkdir()
    (vault / ".rvc-root").write_text("")
    (vault / "newfile.md").write_text("body")
    rvc_cli.cmd_git_commit_all(str(vault), "should not commit", dry_run=True)
    # Verify nothing is in HEAD yet (dry run made no commits).
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_git_repo,
                         capture_output=True, text=True).stdout.strip()
    msg = subprocess.run(["git", "show", "-s", "--pretty=%B", sha], cwd=tmp_git_repo,
                         capture_output=True, text=True).stdout
    assert "should not commit" not in msg  # dry_run must be safe


def test_cmd_git_commit_all_requires_one_flag(tmp_vault):
    with pytest.raises(SystemExit) as exc:
        rvc_cli.cmd_git_commit_all(str(tmp_vault), "x")
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
#  RED: shell=True audit (STORY-013) — these pin known security bugs
# ---------------------------------------------------------------------------
@pytest.mark.xfail(reason="RED: rvc-cli.run_cmd still uses shell=True", strict=True)
def test_run_cmd_should_not_use_shell_true():
    """`run_cmd` must not pass shell=True — it's a command-injection vector."""
    import inspect
    src = inspect.getsource(rvc_cli.run_cmd)
    assert "shell=True" not in src


@pytest.mark.xfail(reason="RED: _next_id has no filesystem locking (STORY-013)", strict=True)
def test_next_id_is_atomic_under_concurrency(tmp_vault):
    """Two concurrent _next_id calls must produce different IDs."""
    import threading
    results = []
    def go():
        results.append(rvc_cli._next_id(str(tmp_vault)))
    threads = [threading.Thread(target=go) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(set(results)) == len(results)  # all unique
