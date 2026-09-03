"""Producing and checking a distributable build.

A release is where every honesty rule in this framework gets tested at once,
because "we shipped it" is the claim people most want to make on the least
evidence. So the four steps below are deliberately separate, and none of them
concludes the next one:

    doctor   — can this project be released at all?
    build    — produce a package
    verify   — check the package that was produced
    package  — record it, with its hash and provenance

Producing a package does not verify it. Verifying that a file exists does not
mean it runs. Smoke-testing a packaged build does not mean the game is good.
Each step says what it established and, more importantly, what it did not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import BuildOptions, OperationAuthorization, resolve_adapter
from .artifacts import ArtifactCreateRequest, ArtifactService, hash_artifact
from .execution import detect_repository
from .state import StateRepository

#: Files whose presence a release depends on. Absence is reported, never fixed:
#: generating a licence file for someone would be worse than saying it is
#: missing.
RELEASE_REQUIRED_FILES = (
    ("LICENSE", "a licence the build may be distributed under"),
    ("THIRD_PARTY_NOTICES.md", "attribution for third-party code and assets"),
)

#: Every check `studio release doctor` performs.
READINESS_CHECKS = (
    "project_identity",
    "version_metadata",
    "licence",
    "third_party_notices",
    "engine_export",
    "revision",
)


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    """One release-readiness finding."""

    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ReleaseReadiness:
    """Whether this project could produce a distributable build."""

    checks: tuple[ReleaseCheck, ...]

    @property
    def status(self) -> str:
        """`ready`, `blocked`, or `unknown` — the worst of the checks."""

        if any(check.status == "failed" for check in self.checks):
            return "blocked"
        if any(check.status == "unknown" for check in self.checks):
            return "unknown"
        return "ready"

    @property
    def blockers(self) -> tuple[ReleaseCheck, ...]:
        return tuple(check for check in self.checks if check.status == "failed")

    @property
    def unknowns(self) -> tuple[ReleaseCheck, ...]:
        return tuple(check for check in self.checks if check.status == "unknown")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [check.to_dict() for check in self.blockers],
            "unknowns": [check.to_dict() for check in self.unknowns],
        }


def check_release_readiness(root: Path) -> ReleaseReadiness:
    """Report whether this project could produce a distributable build."""

    project = StateRepository(root).load_project()
    checks: list[ReleaseCheck] = [
        _identity_check(project),
        _version_check(project),
        *_file_checks(root),
        _export_check(root),
        _revision_check(root),
    ]
    return ReleaseReadiness(checks=tuple(checks))


def _identity_check(project: dict[str, Any]) -> ReleaseCheck:
    if project["project_name"] == "Untitled Game":
        return ReleaseCheck(
            "project_identity",
            "failed",
            "the project is still named 'Untitled Game'; a release needs a name",
        )
    return ReleaseCheck(
        "project_identity", "passed", f"project name is {project['project_name']!r}"
    )


def _version_check(project: dict[str, Any]) -> ReleaseCheck:
    # The framework does not own a game's version number, and inventing one
    # would put a wrong number on a distributed build.
    if not project.get("engine_version"):
        return ReleaseCheck(
            "version_metadata",
            "unknown",
            "no engine version is recorded; the packaged build cannot be traced to one",
        )
    return ReleaseCheck(
        "version_metadata",
        "passed",
        f"engine version {project['engine_version']} is recorded",
    )


def _file_checks(root: Path) -> list[ReleaseCheck]:
    checks: list[ReleaseCheck] = []
    for relative, purpose in RELEASE_REQUIRED_FILES:
        name = "licence" if relative == "LICENSE" else "third_party_notices"
        if (root / relative).is_file():
            checks.append(ReleaseCheck(name, "passed", f"{relative} is present"))
        else:
            checks.append(
                ReleaseCheck(
                    name,
                    "failed",
                    f"{relative} is missing; a release needs {purpose}",
                )
            )
    return checks


def _export_check(root: Path) -> ReleaseCheck:
    adapter = resolve_adapter(root)
    if adapter is None:
        return ReleaseCheck(
            "engine_export",
            "unknown",
            "no engine adapter recognises this project; nothing can be exported "
            "by the framework",
        )
    probe = adapter.probe(root)
    if probe.supports("EXPORT"):
        return ReleaseCheck(
            "engine_export", "passed", probe.capability("EXPORT").detail
        )
    report = probe.capability("EXPORT")
    return ReleaseCheck(
        "engine_export",
        "failed" if report and report.readiness == "unavailable" else "unknown",
        report.detail if report else "export was not probed",
    )


def _revision_check(root: Path) -> ReleaseCheck:
    repository = detect_repository(root)
    if repository["revision"] is None:
        return ReleaseCheck(
            "revision",
            "unknown",
            "no revision could be determined; the package will not be traceable "
            "to a commit",
        )
    if repository["dirty"]:
        # Not a failure: releasing from a dirty tree is a choice. It just cannot
        # be reproduced from the recorded revision, and a reader must know.
        return ReleaseCheck(
            "revision",
            "unknown",
            f"revision {repository['revision'][:12]} has uncommitted changes; "
            "the package cannot be reproduced from it",
        )
    return ReleaseCheck(
        "revision", "passed", f"clean tree at {repository['revision'][:12]}"
    )


@dataclass(frozen=True, slots=True)
class PackagedRelease:
    """A produced package, recorded with everything needed to trace it."""

    artifact_id: str | None
    path: str
    exists: bool
    sha256: str | None
    size_bytes: int | None
    revision: str | None
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "exists": self.exists,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "revision": self.revision,
            "limitations": list(self.limitations),
        }


def package_release(
    root: Path,
    path: str,
    *,
    source_run: str | None = None,
    description: str | None = None,
) -> PackagedRelease:
    """Register a produced package as an artifact, hashed and traceable.

    A package that is not where it was supposed to be is registered as missing
    rather than refused. "The build reported success and produced nothing" is
    precisely the situation worth having on record.
    """

    repository = detect_repository(root)
    result = ArtifactService(root).add(
        ArtifactCreateRequest(
            type="build",
            path=path,
            source_run=source_run,
            revision=repository["revision"],
            description=description or "Release package.",
            metadata={
                "capture_source": "automated-run",
                "release": True,
                "working_tree_dirty": repository["dirty"],
            },
        )
    )
    artifact = result.details["artifact"]
    limitations = [
        (
            "A produced package has not been launched. Nothing here establishes "
            "that it runs."
        ),
    ]
    if repository["dirty"]:
        limitations.append(
            "The working tree had uncommitted changes, so this package cannot "
            "be reproduced from the recorded revision."
        )
    if artifact["status"] == "missing":
        limitations.append(
            "No file exists at the recorded path; the build did not produce "
            "what it promised."
        )
    return PackagedRelease(
        artifact_id=artifact["id"],
        path=artifact["path"],
        exists=artifact["status"] == "present",
        sha256=artifact["sha256"],
        size_bytes=artifact["size_bytes"],
        revision=artifact["revision"],
        limitations=tuple(limitations),
    )


def verify_package(root: Path, artifact_id: str) -> tuple[ReleaseCheck, ...]:
    """Check a recorded package against the file on disk.

    Establishes that the file exists and still hashes to what was recorded. It
    does not establish that the package runs — that needs a smoke test of the
    packaged build, which the framework cannot perform for an arbitrary target.
    """

    state = StateRepository(root).load_artifacts()
    artifact = next(
        (item for item in state["artifacts"] if item["id"] == artifact_id), None
    )
    if artifact is None:
        return (
            ReleaseCheck(
                "package_present", "failed", f"{artifact_id} is not registered"
            ),
        )

    path = Path(artifact["path"])
    resolved = path if path.is_absolute() else root / path
    if not resolved.is_file():
        return (
            ReleaseCheck("package_present", "failed", f"no file at {artifact['path']}"),
        )

    checks = [ReleaseCheck("package_present", "passed", f"{artifact['path']} exists")]
    if artifact["sha256"] is None:
        checks.append(
            ReleaseCheck(
                "package_hash",
                "unknown",
                "the package was registered without a hash; nothing to compare",
            )
        )
    elif hash_artifact(resolved) == artifact["sha256"]:
        checks.append(
            ReleaseCheck("package_hash", "passed", "the file matches its recorded hash")
        )
    else:
        checks.append(
            ReleaseCheck(
                "package_hash",
                "failed",
                "the file no longer matches its recorded hash",
            )
        )
    checks.append(
        ReleaseCheck(
            "package_runs",
            "unknown",
            "the packaged build has not been launched; the framework cannot "
            "smoke-test an arbitrary distributable target",
        )
    )
    return tuple(checks)


def build_release(
    root: Path,
    *,
    target: str | None = None,
    output: str | None = None,
    authorization: OperationAuthorization | None = None,
) -> Any:
    """Produce a release build through the resolved engine adapter."""

    adapter = resolve_adapter(root)
    if adapter is None:
        return None
    return adapter.build(
        root,
        BuildOptions(
            target=target,
            profile="release",
            output=output,
            authorization=authorization or OperationAuthorization(risk_level="medium"),
        ),
    )
