from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_seven_phases_and_twelve_resolved_workflows() -> None:
    catalog = json.loads(
        (REPOSITORY_ROOT / ".studio" / "workflow-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    assert [phase["number"] for phase in catalog["phases"]] == list(range(7))
    assert len(catalog["workflows"]) == 12
    assert len({workflow["alias"] for workflow in catalog["workflows"]}) == 12
    for workflow in catalog["workflows"]:
        assert (REPOSITORY_ROOT / workflow["playbook"]).is_file()
        assert all((REPOSITORY_ROOT / role).is_file() for role in workflow["roles"])
