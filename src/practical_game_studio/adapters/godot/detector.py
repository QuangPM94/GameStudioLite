"""Finding a Godot project and the Godot binary that could run it.

Detection and probing answer different questions, and the split matters. A
`project.godot` file proves this is a Godot project. It proves nothing about
whether Godot is installed on this machine. The framework must be able to say
"this is a Godot project and I cannot run it" — that sentence is the whole
reason `studio doctor` exists.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ...execution import ExecutionRequest, execute_process, which

PROJECT_MANIFEST = "project.godot"

#: Checked in order. `GODOT` lets a developer point at a specific build without
#: putting it on PATH, which is common when several engine versions coexist.
EXECUTABLE_ENVIRONMENT_VARIABLES = ("GODOT", "GODOT4", "GODOT_BIN")

#: Names Godot ships under. Godot 3 and 4 use different binary names on
#: different platforms, and guessing one would produce false negatives.
EXECUTABLE_NAMES = (
    "godot",
    "godot4",
    "Godot",
    "Godot_v4",
    "godot-headless",
    "godot.exe",
)

VERSION_PATTERN = re.compile(r"(\d+\.\d+(?:\.\d+)?)")
PROBE_TIMEOUT_SECONDS = 30.0

#: Test frameworks the adapter knows how to recognise. Absence of all of them is
#: reported as "no test framework", never as a broken project.
TEST_FRAMEWORK_MARKERS = {
    "gdunit4": ("addons/gdUnit4", "addons/gdUnit4/plugin.cfg"),
    "gut": ("addons/gut", "addons/gut/plugin.cfg"),
}


@dataclass(frozen=True, slots=True)
class GodotProject:
    """What was found by looking at the directory."""

    manifest: Path | None
    project_path: Path | None
    export_presets: Path | None
    export_preset_names: tuple[str, ...] = ()
    dotnet: bool = False
    test_framework: str | None = None

    @property
    def found(self) -> bool:
        return self.manifest is not None


@dataclass(frozen=True, slots=True)
class GodotExecutable:
    """What was found by looking for the engine binary."""

    path: Path | None
    version: str | None
    source: str
    detail: str

    @property
    def found(self) -> bool:
        return self.path is not None


def detect_godot_project(root: Path) -> GodotProject:
    """Look for a Godot project at `root` or one directory below it.

    One level down is searched because attaching the framework to a repository
    whose engine project lives in `game/` or `client/` is normal, and refusing
    to look would make the common layout unsupported for no reason.
    """

    manifest = _find_manifest(root)
    if manifest is None:
        return GodotProject(manifest=None, project_path=None, export_presets=None)

    project_path = manifest.parent
    presets = project_path / "export_presets.cfg"
    return GodotProject(
        manifest=manifest,
        project_path=project_path,
        export_presets=presets if presets.is_file() else None,
        export_preset_names=_read_preset_names(presets),
        dotnet=_has_dotnet_indicators(project_path),
        test_framework=_detect_test_framework(project_path),
    )


def _find_manifest(root: Path) -> Path | None:
    direct = root / PROJECT_MANIFEST
    if direct.is_file():
        return direct
    try:
        children = sorted(entry for entry in root.iterdir() if entry.is_dir())
    except OSError:
        return None
    for child in children:
        if child.name.startswith("."):
            continue
        candidate = child / PROJECT_MANIFEST
        if candidate.is_file():
            return candidate
    return None


def _read_preset_names(presets: Path) -> tuple[str, ...]:
    """Read export preset names, tolerating a file we cannot parse.

    Returning an empty tuple lets the caller report "no preset found" rather
    than crashing a doctor run on a hand-edited config.
    """

    if not presets.is_file():
        return ()
    try:
        text = presets.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    return tuple(re.findall(r'^\s*name\s*=\s*"([^"]+)"', text, flags=re.MULTILINE))


def _has_dotnet_indicators(project_path: Path) -> bool:
    if any(project_path.glob("*.csproj")) or any(project_path.glob("*.sln")):
        return True
    try:
        manifest = (project_path / PROJECT_MANIFEST).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False
    return "dotnet" in manifest.lower()


def _detect_test_framework(project_path: Path) -> str | None:
    for name, markers in TEST_FRAMEWORK_MARKERS.items():
        if any((project_path / marker).exists() for marker in markers):
            return name
    return None


def detect_godot_executable() -> GodotExecutable:
    """Find a Godot binary, preferring an explicitly configured one."""

    for variable in EXECUTABLE_ENVIRONMENT_VARIABLES:
        configured = os.environ.get(variable)
        if not configured:
            continue
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return GodotExecutable(
                path=candidate,
                version=None,
                source=f"${variable}",
                detail=f"configured via ${variable}",
            )
        return GodotExecutable(
            path=None,
            version=None,
            source=f"${variable}",
            detail=f"${variable} points at {candidate}, which is not a file",
        )

    for name in EXECUTABLE_NAMES:
        located = which(name)
        if located is not None:
            return GodotExecutable(
                path=located,
                version=None,
                source="PATH",
                detail=f"found {name} on PATH",
            )
    return GodotExecutable(
        path=None,
        version=None,
        source="none",
        detail=(
            "no Godot binary found on PATH or in $GODOT; set $GODOT to the "
            "engine executable to enable run, test, build, and export"
        ),
    )


def get_godot_version(executable: Path) -> str | None:
    """Ask the binary its version, returning None when it will not say.

    None means "we asked and could not tell", which the caller reports as
    `unknown` rather than assuming a version and choosing flags for it.
    """

    result = execute_process(
        ExecutionRequest(
            command=(str(executable), "--version"),
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
    )
    if not result.ok:
        return None
    text = (result.stdout or result.stderr).strip()
    if not text:
        return None
    first = text.splitlines()[0].strip()
    return first or None


def major_version(version: str | None) -> int | None:
    """Extract the major version number, or None when it cannot be read."""

    if not version:
        return None
    match = VERSION_PATTERN.search(version)
    if match is None:
        return None
    return int(match.group(1).split(".")[0])
