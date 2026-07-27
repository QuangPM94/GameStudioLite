from __future__ import annotations

from pathlib import Path

from practical_game_studio.reporting import REPORT_RENDERERS, WARNING, generate_reports

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_report_generation_includes_warning_and_direction_sections() -> None:
    generated = generate_reports(REPOSITORY_ROOT)

    assert len(generated) == len(REPORT_RENDERERS)
    for path in generated:
        assert path.read_text(encoding="utf-8").startswith(WARNING)
    direction = (
        REPOSITORY_ROOT / ".studio" / "reports" / "direction-report.md"
    ).read_text(encoding="utf-8")
    for heading in (
        "## Current State",
        "## What We Learned",
        "## Evidence",
        "## Open Decisions",
        "## Critical Path",
        "## Recommended Next Step",
        "## Do Not Work On Yet",
        "## Next Command",
    ):
        assert heading in direction
