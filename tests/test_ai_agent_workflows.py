"""Contract tests for the AI-agent command layer: new/enhanced workflow
aliases, their playbooks, and the documentation that describes them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS_DIR = REPOSITORY_ROOT / ".studio" / "playbooks"
CATALOG = json.loads(
    (REPOSITORY_ROOT / ".studio" / "workflow-catalog.json").read_text(encoding="utf-8")
)
ALL_CANONICAL_COMMANDS = tuple(
    workflow["canonical"] for workflow in CATALOG["workflows"]
)
NEW_ALIASES = (
    "/resume",
    "/project-status",
    "/report-issue",
    "/record-evidence",
    "/decision",
    "/milestone-criteria",
)
ALL_DOCUMENTED_ALIASES = NEW_ALIASES + ("/critical-path", "/next-step")
READ_ONLY_NEW_ALIASES = ("resume", "project-status")
MUTATING_NEW_ALIASES = (
    "report-issue",
    "record-evidence",
    "decision",
    "milestone-criteria",
)


def _read(relative: str) -> str:
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


def _playbook(name: str) -> str:
    return (PLAYBOOKS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    body = text.split(f"## {heading}")[1]
    return body.split("\n## ")[0]


@pytest.mark.parametrize("alias", ALL_DOCUMENTED_ALIASES)
def test_readme_references_every_user_facing_alias(alias: str) -> None:
    readme = _read("README.md")
    assert f"`{alias}`" in readme, f"README.md does not document {alias}"


@pytest.mark.parametrize("canonical", ALL_CANONICAL_COMMANDS)
def test_readme_documents_every_canonical_command(canonical: str) -> None:
    readme = _read("README.md")
    assert f"`{canonical}`" in readme, f"README.md does not document {canonical}"


def test_readme_explains_gs_syntax_works_across_ai_clients() -> None:
    readme = _read("README.md").lower()
    assert "plain text" in readme
    assert "slash command" in readme
    assert "@" in readme
    assert "mention" in readme


def test_agents_md_explains_cli_backed_mutation() -> None:
    agents = _read("AGENTS.md")
    assert "studio issue add" in agents
    assert "studio decision resolve" in agents
    # Every canonical-state command family must point at supported commands
    # instead of direct JSON edits.
    assert "Prefer these commands over direct edits to" in agents
    assert agents.count("direct edits to") >= 3


def test_agents_md_title_is_ai_client_neutral() -> None:
    agents = _read("AGENTS.md")
    assert "Codex Instructions" not in agents
    assert "AI Agent Instructions" in agents
    assert agents.splitlines()[0] == "# Practical Game Studio — AI Agent Instructions"


def test_agents_md_canonical_state_forbids_manual_edits() -> None:
    agents = _read("AGENTS.md")
    assert (
        "JSON under `.studio/state/` is the sole canonical source of project "
        "state. AI workflows must use the studio CLI and must not edit it "
        "manually" in agents
    )
    assert "sole manually editable source" not in agents


def test_resume_legacy_alias_is_only_resume() -> None:
    text = _playbook("resume")
    when_to_use = _section(text, "When to use")
    assert "Legacy alias: `/resume`." in when_to_use
    assert "/start" not in when_to_use


def test_resume_and_start_distinguish_new_vs_existing_initialized_projects() -> None:
    resume_text = _playbook("resume").lower()
    assert "already-initialized" in resume_text

    start_text = _playbook("start").lower()
    assert "new, unknown, uninitialized, or intake-stage" in start_text
    assert "gs:resume" in start_text


def test_readme_prefers_gs_start_in_fallback_examples() -> None:
    readme = _read("README.md")
    assert "Read AGENTS.md and execute the GS:start workflow." in readme
    assert "Read AGENTS.md and execute the /start workflow." not in readme


@pytest.mark.parametrize("name", READ_ONLY_NEW_ALIASES)
def test_read_only_new_playbooks_declare_no_state_changes(name: str) -> None:
    text = _playbook(name)
    state_changes = _section(text, "State changes")
    assert state_changes.strip().startswith("None.")
    assert "edit `.studio/state/" not in text


@pytest.mark.parametrize("name", MUTATING_NEW_ALIASES)
def test_mutating_new_playbooks_forbid_direct_json_edits(name: str) -> None:
    text = _playbook(name)
    state_changes = _section(text, "State changes")
    assert "never edit" in state_changes.lower()
    assert ".studio/state/" in state_changes
    assert "directly" in state_changes.lower()


def test_project_status_is_read_only_by_contract() -> None:
    text = _playbook("project-status")
    state_changes = _section(text, "State changes").lower()
    assert "never writes state" in state_changes
    assert "never recalculates the critical path" in state_changes


def test_next_step_is_read_only_by_contract() -> None:
    text = _playbook("next-step")
    state_changes = _section(text, "State changes").lower()
    assert "read-only" in state_changes
    assert (
        "do not run `studio path calculate` from inside `gs:next-step`" in text.lower()
    )


def test_resume_prohibits_normal_bootstrap_and_init() -> None:
    text = _playbook("resume").lower()
    assert "never runs `studio bootstrap` or `studio init`" in text
    assert "never resets phase, milestone, issues, decisions" in text


def test_record_evidence_preserves_observed_vs_user_reported_semantics() -> None:
    text = _playbook("record-evidence").lower()
    assert "user-reported" in text
    assert "observed" in text
    assert "is `user-reported`, not `observed`" in text


def test_decision_preserves_user_decision_authority() -> None:
    text = _playbook("decision").lower()
    assert (
        "resolve the decision with `studio decision resolve` only when the user" in text
    )
    assert "never resolve on the agent's own recommendation" in text


def test_milestone_criteria_requires_explicit_evaluation() -> None:
    text = _playbook("milestone-criteria").lower()
    assert "explicit `studio criterion evaluate` result" in text
    assert "never counts as verification by itself" in text


@pytest.mark.parametrize("name", MUTATING_NEW_ALIASES)
def test_mutating_new_playbooks_run_validate_and_path_check(name: str) -> None:
    text = _playbook(name)
    assert "studio validate" in text
    assert "studio path check" in text
