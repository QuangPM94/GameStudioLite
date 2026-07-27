"""Typed results shared by core services and the CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationResult:
    """Accumulated validation errors."""

    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, message: str) -> None:
        self.errors.append(message)


@dataclass(frozen=True, slots=True)
class StatusSummary:
    """Human-readable status values derived from canonical state."""

    phase: str
    milestone: str
    build_status: str
    open_issues_by_severity: dict[str, int]
    pending_decisions: list[str]
    critical_path_items: list[str]
    recommended_next_playbook: str


@dataclass(frozen=True, slots=True)
class MutationResult:
    """Structured outcome from a state mutation operation."""

    success: bool
    operation: str
    changed_files: tuple[str, ...]
    unchanged_files: tuple[str, ...]
    warnings: tuple[str, ...]
    validation_summary: dict[str, Any]
    report_summary: dict[str, Any]
    dry_run: bool
    changed_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation for future machine output."""

        return asdict(self)
