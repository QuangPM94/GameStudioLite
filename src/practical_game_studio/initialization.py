"""Project detection and transactional ``studio init`` service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import MutationResult
from .reporting import render_report_contents
from .state import StateRepository
from .transaction import ReportRenderer, StateTransaction

PLACEHOLDER_PROJECT_NAME = "Untitled Game"
INITIAL_MILESTONE = "Clarify the game idea"
INITIAL_ASSUMPTION = (
    "No game concept, engine, platform, or build has been recorded yet."
)
REVIEW_MODES = {"fast", "guided", "strict"}


class InitializationError(ValueError):
    """Initialization input is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class InitRequest:
    """Normalized inputs for project initialization."""

    name: str | None = None
    engine: str | None = None
    engine_version: str | None = None
    platform: str | None = None
    genre: str | None = None
    review_mode: str | None = None
    force: bool = False
    dry_run: bool = False
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class EngineDetection:
    """Conservative engine indicators found without modifying the project."""

    engine: str | None
    indicators: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]


def is_placeholder_project(project: dict[str, Any]) -> bool:
    """Return whether canonical project identity still has the Phase A placeholder."""

    return project.get("project_name") == PLACEHOLDER_PROJECT_NAME


def _clean_optional(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise InitializationError(f"{field} cannot be empty")
    return cleaned


def _normalize_engine(value: str | None) -> str | None:
    cleaned = _clean_optional(value, "engine")
    if cleaned is None:
        return None
    known = {"unity": "Unity", "godot": "Godot", "unreal": "Unreal"}
    return known.get(cleaned.casefold(), cleaned)


def detect_engine(root: Path) -> EngineDetection:
    """Inspect common local engine markers without claiming more than they prove."""

    root = root.resolve()
    indicators: dict[str, tuple[str, ...]] = {}
    if (root / "Assets").is_dir() and (root / "ProjectSettings").is_dir():
        indicators["Unity"] = ("Assets/", "ProjectSettings/")
    if (root / "project.godot").is_file():
        indicators["Godot"] = ("project.godot",)
    unreal_projects = tuple(
        path.name
        for path in sorted(root.glob("*.uproject"), key=lambda item: item.name)
    )
    if unreal_projects:
        indicators["Unreal"] = unreal_projects

    warnings: list[str] = []
    engine: str | None = None
    if len(indicators) == 1:
        engine = next(iter(indicators))
    elif len(indicators) > 1:
        names = ", ".join(indicators)
        warnings.append(
            f"Multiple engine indicators were detected ({names}); engine remains unknown "
            "unless --engine is supplied."
        )
    return EngineDetection(
        engine=engine, indicators=indicators, warnings=tuple(warnings)
    )


def initialize_project(
    root: Path,
    request: InitRequest,
    *,
    report_renderer: ReportRenderer = render_report_contents,
) -> MutationResult:
    """Initialize or explicitly update project identity through one transaction."""

    root = root.resolve()
    repository = StateRepository(root)
    existing = repository.load_project()
    placeholder = is_placeholder_project(existing)

    name = _clean_optional(request.name, "name")
    engine = _normalize_engine(request.engine)
    engine_version = _clean_optional(request.engine_version, "engine version")
    platform = _clean_optional(request.platform, "platform")
    genre = _clean_optional(request.genre, "genre")
    if request.review_mode is not None and request.review_mode not in REVIEW_MODES:
        allowed = ", ".join(sorted(REVIEW_MODES))
        raise InitializationError(f"review mode must be one of: {allowed}")
    if placeholder and name is None:
        raise InitializationError("missing required value: --name")
    if request.force and not request.dry_run and not request.acknowledged:
        raise InitializationError(
            "forced initialization requires explicit acknowledgement (--yes)"
        )

    detection = detect_engine(root)
    warnings = list(detection.warnings if engine is None else ())
    if engine is not None and len(detection.indicators) > 1:
        names = ", ".join(detection.indicators)
        warnings.append(
            f"Multiple engine indicators were detected ({names}); using explicit "
            f"engine {engine}."
        )
    if (
        engine is not None
        and detection.engine is not None
        and engine != detection.engine
    ):
        warnings.append(
            f"Detected {detection.engine} indicators but explicit engine is {engine}; "
            "using the explicit value."
        )

    with StateTransaction(
        root,
        operation="project-init",
        dry_run=request.dry_run,
        report_renderer=report_renderer,
    ) as transaction:
        project = transaction.state["project"]
        changed_fields: dict[str, dict[str, Any]] = {}
        already_initialized = not placeholder

        if already_initialized and not request.force:
            warnings.append(
                "Project is already initialized; no state was changed. "
                "Use 'studio status' or pass --force with explicit fields."
            )
        else:
            updates: dict[str, Any] = {}
            if placeholder:
                updates = {
                    "project_name": name,
                    "engine": engine if engine is not None else detection.engine,
                    "engine_version": engine_version,
                    "platform": platform,
                    "genre": genre,
                    "current_phase": "intake",
                    "current_milestone": INITIAL_MILESTONE,
                    "current_build_status": (
                        "unknown" if detection.indicators else "not-built"
                    ),
                    "review_mode": request.review_mode or "guided",
                    "recommended_next_playbook": "/start",
                    "known_assumptions": [
                        item
                        for item in project["known_assumptions"]
                        if item != INITIAL_ASSUMPTION
                    ],
                }
            else:
                explicit_updates = {
                    "project_name": name,
                    "engine": engine,
                    "engine_version": engine_version,
                    "platform": platform,
                    "genre": genre,
                    "review_mode": request.review_mode,
                }
                updates = {
                    field: value
                    for field, value in explicit_updates.items()
                    if value is not None
                }

            for field, value in updates.items():
                if project.get(field) != value:
                    changed_fields[field] = {"old": project.get(field), "new": value}
                    project[field] = value
            if changed_fields:
                transaction.set_project(project)

        details = {
            "project": project,
            "already_initialized": already_initialized,
            "engine_detection": {
                "engine": detection.engine,
                "indicators": detection.indicators,
            },
            "recommended_next_workflow": project["recommended_next_playbook"],
        }
        return transaction.commit(
            warnings=warnings,
            changed_fields=changed_fields,
            details=details,
        )
