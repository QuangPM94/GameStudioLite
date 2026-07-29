from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio.workflow_commands import (
    MalformedInvocationError,
    UnknownWorkflowError,
    WorkflowCommand,
    parse_invocation,
    valid_canonical_commands,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalog() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / ".studio" / "workflow-catalog.json").read_text(
            encoding="utf-8"
        )
    )


def test_every_canonical_invocation_is_unique(catalog: dict) -> None:
    canonicals = [workflow["canonical"] for workflow in catalog["workflows"]]
    assert len(canonicals) == len(set(canonicals))


def test_every_canonical_invocation_maps_to_an_existing_playbook(
    catalog: dict,
) -> None:
    for workflow in catalog["workflows"]:
        assert workflow["canonical"].startswith("GS:")
        playbook_path = REPOSITORY_ROOT / workflow["playbook"]
        assert playbook_path.is_file(), workflow["canonical"]


def test_legacy_aliases_cannot_conflict_with_canonical_invocations(
    catalog: dict,
) -> None:
    aliases = {workflow["alias"] for workflow in catalog["workflows"]}
    canonicals = {workflow["canonical"] for workflow in catalog["workflows"]}
    assert aliases.isdisjoint(canonicals)
    for alias in aliases:
        assert not alias.startswith("GS:")
    for canonical in canonicals:
        assert not canonical.startswith(("/", "\\", "@", "!"))


@pytest.mark.parametrize(
    "message",
    [
        "GS:clarify",
        "GS:clarify\nSome input text.",
        "   GS:clarify  \nSome input text.",
        "\n\n  GS:clarify\nSome input text.",
    ],
)
def test_parses_a_well_formed_canonical_invocation(catalog: dict, message: str) -> None:
    command = parse_invocation(message, catalog)
    assert isinstance(command, WorkflowCommand)
    assert command.workflow_id == "clarify"
    assert command.canonical == "GS:clarify"


def test_input_text_is_everything_after_the_first_command_line(
    catalog: dict,
) -> None:
    message = "GS:report-issue\n\nDefender can place two towers in the same slot."
    command = parse_invocation(message, catalog)
    assert command is not None
    assert command.input_text == "Defender can place two towers in the same slot."


@pytest.mark.parametrize(
    "message",
    [
        "Hello, can you help me with this bug?",
        "/clarify",
        "/report-issue\n\nSomething broke.",
        "",
        "gs:clarify",
    ],
)
def test_non_gs_prefixed_text_is_not_treated_as_a_command(
    catalog: dict, message: str
) -> None:
    assert parse_invocation(message, catalog) is None


@pytest.mark.parametrize(
    "message",
    [
        "GS:",
        "GS:/clarify",
        "GS:Clarify",
        "GS: clarify",
        "GS::clarify",
        "GS:clarify-",
        "GS:-clarify",
    ],
)
def test_malformed_commands_are_rejected(catalog: dict, message: str) -> None:
    with pytest.raises(MalformedInvocationError):
        parse_invocation(message, catalog)


def test_unknown_workflow_ids_are_rejected_and_list_valid_commands(
    catalog: dict,
) -> None:
    with pytest.raises(UnknownWorkflowError) as excinfo:
        parse_invocation("GS:not-a-real-workflow", catalog)

    error = excinfo.value
    assert error.workflow_id == "not-a-real-workflow"
    assert error.valid_canonicals == valid_canonical_commands(catalog)
    assert "GS:clarify" in error.valid_canonicals
    assert "GS:not-a-real-workflow" in str(error)


def test_valid_canonical_commands_cover_every_catalog_workflow(
    catalog: dict,
) -> None:
    expected = {workflow["canonical"] for workflow in catalog["workflows"]}
    assert set(valid_canonical_commands(catalog)) == expected
