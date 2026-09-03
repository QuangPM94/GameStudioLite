"""Optional providers, media provenance, and release tooling.

The rule these three share: the framework may only claim what it has actually
established. A provider it cannot reach offers nothing. A screenshot with no
recorded provenance supports nothing. A package that exists has not been run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from practical_game_studio import cli
from practical_game_studio.artifacts import ArtifactCreateRequest, ArtifactService
from practical_game_studio.bootstrap import BootstrapRequest, BootstrapService
from practical_game_studio.evidence import (
    EvidenceCreateRequest,
    EvidenceInputError,
    EvidenceService,
)
from practical_game_studio.provenance import (
    assess,
    capture_source,
    strongest_supported_classification,
    supports_player_behavior,
)
from practical_game_studio.providers import (
    BaseProvider,
    ProviderHealth,
    ProviderNotFoundError,
    get_provider,
    probe_providers,
    provider_capabilities,
    register_provider,
    unregister_provider,
)
from practical_game_studio.release import (
    check_release_readiness,
    package_release,
    verify_package,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    BootstrapService(tmp_path).bootstrap(
        BootstrapRequest(name="Release Demo", engine="Godot")
    )
    return tmp_path


def _write(path: Path, text: str = "content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _register_media(
    root: Path, name: str, *, artifact_type: str = "screenshot", source: str = "unknown"
) -> str:
    path = _write(root / name)
    return (
        ArtifactService(root)
        .add(
            ArtifactCreateRequest(
                type=artifact_type,
                path=str(path),
                metadata={"capture_source": source},
            )
        )
        .details["artifact_id"]
    )


# --- providers ---------------------------------------------------------------


def test_a_project_with_no_provider_configured_is_normal(project: Path) -> None:
    """The framework must work fully without MCP."""

    probes = probe_providers(project)

    assert probes
    assert all(probe.health.status == "not-configured" for probe in probes)
    assert provider_capabilities(project) == ()


def test_a_configured_provider_is_still_not_claimed_as_usable(project: Path) -> None:
    """A config file proves configuration, not reachability."""

    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"godot-mcp": {"command": "godot-mcp"}}}),
        encoding="utf-8",
    )

    probe = get_provider("godot-mcp").probe(project)

    assert probe.health.status == "unknown"
    assert probe.health.configuration == ".mcp.json"
    assert probe.available_capabilities == ()
    assert not probe.supports("SCREENSHOT")


def test_an_unreachable_provider_supports_nothing(project: Path) -> None:
    class Optimistic(BaseProvider):
        id = "optimistic"
        display_name = "Optimistic"

        def detect(self, root: Path) -> bool:
            return True

        def health(self, root: Path) -> ProviderHealth:
            return ProviderHealth(status="unreachable", detail="not running")

        def capabilities(self, root: Path):
            from practical_game_studio.providers import ProviderCapability

            return (
                ProviderCapability("SCREENSHOT", "ready", "stable", "claims it can"),
            )

    register_provider(Optimistic(), replace=True)
    try:
        probe = get_provider("optimistic").probe(project)

        # The capability is still listed, so a reader can see what configuring
        # it would buy — but nothing can act on it.
        assert probe.capability("SCREENSHOT").available
        assert not probe.supports("SCREENSHOT")
        assert probe.available_capabilities == ()
    finally:
        unregister_provider("optimistic")


def test_the_godot_provider_states_its_evidence_policy(project: Path) -> None:
    probe = get_provider("godot-mcp").probe(project)

    joined = " ".join(probe.evidence_policy)
    assert "not evidence about a player" in joined
    assert "Injected input is not player behaviour" in joined


def test_an_unknown_provider_names_what_is_registered() -> None:
    with pytest.raises(ProviderNotFoundError, match="godot-mcp"):
        get_provider("no-such-provider")


def test_doctor_reports_providers_without_claiming_them(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["doctor", "--root", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["data"]["providers"]["readiness"] == "not-configured"
    assert payload["data"]["providers"]["available"] == []


def test_provider_doctor_says_providers_are_optional(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["provider", "list", "--root", str(project)]) == 0

    assert "optional" in capsys.readouterr().out


# --- media provenance ---------------------------------------------------------


def test_media_with_no_recorded_provenance_supports_nothing() -> None:
    """A `.png` says nothing about who was at the keyboard."""

    assert capture_source({"metadata": {}}) == "unknown"
    assert strongest_supported_classification("unknown") == "unknown"
    assert not supports_player_behavior("unknown")


def test_a_developer_session_is_not_player_behaviour() -> None:
    """Someone who built the thing cannot be surprised by it."""

    assert strongest_supported_classification("developer-session") == "observed"
    assert not supports_player_behavior("developer-session")


def test_injected_input_is_not_player_behaviour() -> None:
    assert not supports_player_behavior("provider-capture")
    assert not supports_player_behavior("automated-run")


def test_a_human_playtest_can_support_player_behaviour() -> None:
    assert supports_player_behavior("human-playtest")
    assert strongest_supported_classification("human-playtest") == "observed"


def test_an_external_report_is_user_reported_at_best() -> None:
    assert strongest_supported_classification("external-report") == "user-reported"


def test_assessment_explains_why_a_claim_is_unsupported() -> None:
    artifact = {"id": "ART-0001", "type": "screenshot", "metadata": {}}

    assessment = assess(artifact, "observed")

    assert not assessment.supported
    assert "ART-0001" in assessment.reason
    assert assessment.strongest_supported == "unknown"
    assert any("single frame" in item for item in assessment.limitations)


def test_evidence_cannot_out_run_the_media_it_cites(project: Path) -> None:
    """A folder of screenshots must not become proof of a working game."""

    artifact_id = _register_media(project, "shot.png")

    with pytest.raises(EvidenceInputError, match="cannot support"):
        EvidenceService(project).create_evidence(
            EvidenceCreateRequest(
                title="It works",
                claim="Players complete the delivery loop.",
                classification="observed",
                source_type="screenshot",
                source="shot.png",
                related_artifacts=(artifact_id,),
            )
        )


def test_evidence_backed_by_a_playtest_recording_is_accepted(project: Path) -> None:
    artifact_id = _register_media(project, "play.png", source="human-playtest")

    result = EvidenceService(project).create_evidence(
        EvidenceCreateRequest(
            title="Playtest frame",
            claim="A player reached the delivery screen.",
            classification="observed",
            source_type="human-playtest",
            source="playtest recording",
            related_artifacts=(artifact_id,),
        )
    )

    assert result.details["evidence"]["related_artifacts"] == [artifact_id]


def test_a_cited_log_is_not_subject_to_media_provenance(project: Path) -> None:
    """The rule targets media that looks like proof of play, not build logs."""

    log = _write(project / "build.log")
    artifact_id = (
        ArtifactService(project)
        .add(ArtifactCreateRequest(type="log", path=str(log)))
        .details["artifact_id"]
    )

    result = EvidenceService(project).create_evidence(
        EvidenceCreateRequest(
            title="Build log",
            claim="The build completed without errors.",
            classification="observed",
            source_type="build-log",
            source="build.log",
            related_artifacts=(artifact_id,),
        )
    )

    assert result.success


def test_artifact_add_prints_the_provenance_constraint(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(project / "frame.png")

    cli.main(
        [
            "artifact",
            "add",
            "--root",
            str(project),
            "--type",
            "screenshot",
            "--path",
            str(path),
            "--capture-source",
            "developer-session",
            "--yes",
        ]
    )
    output = capsys.readouterr().out

    assert "'developer-session'" in output
    assert "cannot be surprised by it" in output


# --- release ------------------------------------------------------------------


def test_release_doctor_names_every_missing_prerequisite(project: Path) -> None:
    readiness = check_release_readiness(project)

    names = {check.name for check in readiness.checks}
    assert names == {
        "project_identity",
        "version_metadata",
        "licence",
        "third_party_notices",
        "engine_export",
        "revision",
    }
    assert readiness.status == "blocked"
    assert {check.name for check in readiness.blockers} >= {"licence"}


def test_a_missing_licence_blocks_a_release(project: Path) -> None:
    """Absence is reported, never fixed."""

    readiness = check_release_readiness(project)
    licence = next(c for c in readiness.checks if c.name == "licence")

    assert licence.status == "failed"
    assert not (project / "LICENSE").exists()


def test_a_dirty_tree_is_unknown_rather_than_a_failure(project: Path) -> None:
    """Releasing from a dirty tree is a choice, not an error."""

    readiness = check_release_readiness(project)
    revision = next(c for c in readiness.checks if c.name == "revision")

    assert revision.status == "unknown"
    assert revision.status != "failed"


def test_packaging_records_the_hash_and_revision(project: Path) -> None:
    package = _write(project / "dist" / "game.zip", "binary")

    packaged = package_release(project, str(package))

    assert packaged.exists
    assert packaged.sha256
    assert packaged.artifact_id


def test_packaging_never_claims_the_build_runs(project: Path) -> None:
    package = _write(project / "dist" / "game.zip", "binary")

    packaged = package_release(project, str(package))

    assert any("has not been launched" in item for item in packaged.limitations)


def test_a_build_that_produced_nothing_is_recorded_as_missing(project: Path) -> None:
    """ "Reported success and produced nothing" is worth having on record."""

    packaged = package_release(project, "dist/never-written.zip")

    assert not packaged.exists
    assert any("did not produce" in item for item in packaged.limitations)


def test_verifying_a_package_never_concludes_that_it_runs(project: Path) -> None:
    package = _write(project / "dist" / "game.zip", "binary")
    artifact_id = package_release(project, str(package)).artifact_id

    checks = verify_package(project, artifact_id)

    by_name = {check.name: check for check in checks}
    assert by_name["package_present"].status == "passed"
    assert by_name["package_hash"].status == "passed"
    assert by_name["package_runs"].status == "unknown"


def test_verification_detects_a_package_that_changed(project: Path) -> None:
    package = _write(project / "dist" / "game.zip", "binary")
    artifact_id = package_release(project, str(package)).artifact_id
    package.write_text("tampered", encoding="utf-8")

    by_name = {check.name: check for check in verify_package(project, artifact_id)}

    assert by_name["package_hash"].status == "failed"


def test_release_doctor_exits_non_zero_when_blocked(project: Path) -> None:
    assert cli.main(["release", "doctor", "--root", str(project)]) == 1


def test_release_verify_exits_unknown_because_the_package_was_not_run(
    project: Path,
) -> None:
    package = _write(project / "dist" / "game.zip", "binary")
    artifact_id = package_release(project, str(package)).artifact_id

    assert cli.main(["release", "verify", artifact_id, "--root", str(project)]) == 4
