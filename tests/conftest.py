from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from practical_game_studio.reporting import REPORT_RENDERERS
from practical_game_studio.state import STATE_FILES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def framework_repo() -> Iterator[Path]:
    scratch_root = REPOSITORY_ROOT / ".test-runtime"
    scratch_root.mkdir(exist_ok=True)
    root = scratch_root / uuid.uuid4().hex
    root.mkdir()
    shutil.copytree(REPOSITORY_ROOT / ".studio", root / ".studio")
    for name in ("AGENTS.md", "pyproject.toml"):
        shutil.copy2(REPOSITORY_ROOT / name, root / name)
    try:
        yield root
    finally:
        shutil.rmtree(root)
        if scratch_root.exists() and not any(scratch_root.iterdir()):
            scratch_root.rmdir()


def managed_bytes(root: Path) -> dict[str, bytes]:
    paths = [root / ".studio" / "state" / filename for filename in STATE_FILES.values()]
    paths.extend(
        root / ".studio" / "reports" / filename for filename in REPORT_RENDERERS
    )
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in paths
        if path.exists()
    }
