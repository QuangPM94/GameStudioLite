from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from practical_game_studio.scaffold import load_scaffold_files

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"command failed ({result.returncode}): {' '.join(command)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("pgs-wheel-build")
    source = root / "source"
    shutil.copytree(
        REPOSITORY_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
            ".test-runtime",
            "__pycache__",
            "*.egg-info",
            "build",
            "dist",
        ),
    )
    output = root / "dist"
    output.mkdir()
    _run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(output)],
        cwd=source,
    )
    wheels = sorted(output.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_importlib_resources_exposes_complete_scaffold() -> None:
    files = load_scaffold_files()

    assert "AGENTS.md" in files
    assert ".studio/framework.json" in files
    assert ".studio/state/project.json" in files
    assert list(files) == sorted(files)


def test_built_wheel_contains_every_scaffold_resource(built_wheel: Path) -> None:
    expected = {
        f"practical_game_studio/scaffold/{relative}"
        for relative in load_scaffold_files()
    }
    with zipfile.ZipFile(built_wheel) as archive:
        names = set(archive.namelist())

    assert expected <= names
    assert not any(
        name.startswith(
            (
                "practical_game_studio/scaffold/src/",
                "practical_game_studio/scaffold/tests/",
                "practical_game_studio/scaffold/docs/",
                "practical_game_studio/scaffold/.github/",
                "practical_game_studio/scaffold/.git/",
            )
        )
        for name in names
    )


def test_wheel_installed_cli_bootstraps_without_source_checkout(
    built_wheel: Path, tmp_path: Path
) -> None:
    venv_root = tmp_path / "venv"
    _run([sys.executable, "-m", "venv", str(venv_root)], cwd=tmp_path)
    scripts = venv_root / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    studio = scripts / ("studio.exe" if os.name == "nt" else "studio")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    _run(
        [str(python), "-m", "pip", "install", str(built_wheel)],
        cwd=tmp_path,
        environment=environment,
    )
    game = tmp_path / "WheelGame"
    game.mkdir()
    _run([str(studio), "bootstrap"], cwd=game, environment=environment)
    _run(
        [str(studio), "init", "--name", "Wheel Test Game"],
        cwd=game,
        environment=environment,
    )
    _run([str(studio), "validate"], cwd=game, environment=environment)
    imported = _run(
        [
            str(python),
            "-c",
            "import practical_game_studio as p; print(p.__file__)",
        ],
        cwd=game,
        environment=environment,
    )

    assert str(REPOSITORY_ROOT).casefold() not in imported.stdout.casefold()
    assert (game / ".studio" / "state" / "project.json").is_file()
    assert not (game / "src").exists()
    assert not (game / "tests").exists()
    assert not (game / "docs").exists()
    assert not (game / "pyproject.toml").exists()
