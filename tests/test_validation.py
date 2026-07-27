from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from practical_game_studio.validation import validate_project

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_repository_validates() -> None:
    result = validate_project(REPOSITORY_ROOT)
    assert result.ok, "\n".join(result.errors)


def test_invalid_severity_fails_schema_validation() -> None:
    schema = json.loads(
        (REPOSITORY_ROOT / ".studio" / "schemas" / "issues.schema.json").read_text(
            encoding="utf-8"
        )
    )
    payload = {"schema_version": "1.0", "issues": []}
    payload["issues"].append(
        {
            "id": "ISS-001",
            "title": "Invalid severity",
            "description": "Fixture exercises schema validation.",
            "severity": "catastrophic",
            "category": "other",
            "status": "open",
            "phase_discovered": "intake",
            "evidence_type": "UNKNOWN",
            "evidence_references": [],
            "player_impact": "Unknown",
            "milestone_impact": "Unknown",
            "recommended_action": "Classify correctly",
            "alternative_actions": [],
            "effort": "unknown",
            "dependencies": [],
            "issues_blocked": [],
            "on_critical_path": False,
            "user_decision_required": False,
            "owner": "unassigned",
            "resolution": None,
            "created_at": "2026-07-27T00:00:00Z",
            "updated_at": "2026-07-27T00:00:00Z",
        }
    )
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors
    assert any("catastrophic" in error.message for error in errors)
