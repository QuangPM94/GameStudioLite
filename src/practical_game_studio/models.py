"""Small typed result models used by the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field


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
