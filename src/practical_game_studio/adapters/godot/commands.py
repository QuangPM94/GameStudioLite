"""Building the exact argv the Godot adapter runs.

Kept apart from the adapter so the command lines can be asserted in tests
without a Godot installation. What the framework runs on a developer's machine
is worth being able to read and check directly.
"""

from __future__ import annotations

from pathlib import Path

from ..base import BuildOptions, RunOptions, TestOptions

#: Godot 4 spells the project path `--path`. Passing it explicitly rather than
#: relying on the working directory keeps the recorded command self-describing.
PATH_FLAG = "--path"


def run_command(
    executable: str, project_path: Path, options: RunOptions
) -> tuple[str, ...]:
    """Argv for launching the game."""

    command = [executable, PATH_FLAG, str(project_path)]
    if options.headless:
        command.append("--headless")
    if options.scene:
        command.append(str(options.scene))
    command.extend(options.extra_args)
    return tuple(command)


def test_command(
    executable: str,
    project_path: Path,
    framework: str | None,
    options: TestOptions,
) -> tuple[str, ...]:
    """Argv for running the project's tests with the detected framework."""

    if framework == "gdunit4":
        command = [
            executable,
            PATH_FLAG,
            str(project_path),
            "--headless",
            "-s",
            "res://addons/gdUnit4/bin/GdUnitCmdTool.gd",
            "-a",
            _gdunit_target(options),
        ]
    elif framework == "gut":
        command = [
            executable,
            PATH_FLAG,
            str(project_path),
            "--headless",
            "-s",
            "res://addons/gut/gut_cmdln.gd",
            "-gdir=res://test",
            "-gexit",
        ]
    else:  # pragma: no cover - the adapter refuses before reaching here
        raise ValueError(f"no command is known for test framework {framework!r}")
    command.extend(options.extra_args)
    return tuple(command)


def _gdunit_target(options: TestOptions) -> str:
    """Map a requested suite onto a directory gdUnit4 understands."""

    return {
        "unit": "res://test/unit",
        "scene": "res://test/scene",
        "integration": "res://test/integration",
    }.get(options.suite, "res://test")


def build_command(
    executable: str, project_path: Path, preset: str, options: BuildOptions
) -> tuple[tuple[str, ...], str]:
    """Argv and output path for a build, which for Godot is an export."""

    return export_command(executable, project_path, preset, options)


def export_command(
    executable: str, project_path: Path, preset: str, options: BuildOptions
) -> tuple[tuple[str, ...], str]:
    """Argv and output path for an export.

    Returns the output path alongside the command so the caller can register the
    produced file as an artifact — including when it was never produced, which is
    exactly the case worth recording.
    """

    output = options.output or _default_output(project_path, preset, options.profile)
    flag = "--export-release" if options.profile == "release" else "--export-debug"
    command = [
        executable,
        PATH_FLAG,
        str(project_path),
        "--headless",
        flag,
        preset,
        output,
    ]
    command.extend(options.extra_args)
    return tuple(command), output


def _default_output(project_path: Path, preset: str, profile: str) -> str:
    slug = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in preset
    ).strip("-")
    return str(project_path / "build" / profile / (slug or "export"))
