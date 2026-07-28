"""Packaged lightweight project-scaffold resources and synchronization helpers."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

FRAMEWORK_NAME = "Practical Game Studio"
SCAFFOLD_VERSION = "1.0"
SCAFFOLD_PACKAGE_DIRECTORY = "scaffold"
FRAMEWORK_MANIFEST_PATH = ".studio/framework.json"

PROTECTED_PREFIXES = (".studio/state/", ".studio/reports/")
REPLACEABLE_PREFIXES = (
    "AGENTS.md",
    ".studio/config.json",
    FRAMEWORK_MANIFEST_PATH,
    ".studio/workflow-catalog.json",
    ".studio/roles/",
    ".studio/playbooks/",
    ".studio/schemas/",
    ".studio/templates/",
)
MANAGED_PATHS = (
    "AGENTS.md",
    ".studio/config.json",
    FRAMEWORK_MANIFEST_PATH,
    ".studio/workflow-catalog.json",
    ".studio/roles",
    ".studio/playbooks",
    ".studio/schemas",
    ".studio/templates",
)


class ScaffoldResourceError(RuntimeError):
    """Packaged project scaffold resources are missing or unreadable."""


def _walk_files(node: Traversable, prefix: str = "") -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    try:
        children = sorted(node.iterdir(), key=lambda item: item.name)
    except (FileNotFoundError, OSError) as exc:
        raise ScaffoldResourceError(f"could not read packaged scaffold: {exc}") from exc
    for child in children:
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            files.extend(_walk_files(child, relative))
        elif child.is_file():
            try:
                files.append((relative, child.read_bytes()))
            except OSError as exc:
                raise ScaffoldResourceError(
                    f"could not read packaged scaffold file {relative}: {exc}"
                ) from exc
    return files


def load_scaffold_files() -> dict[str, bytes]:
    """Load every packaged scaffold file in deterministic relative-path order."""

    try:
        root = resources.files("practical_game_studio").joinpath(
            SCAFFOLD_PACKAGE_DIRECTORY
        )
    except (ModuleNotFoundError, TypeError) as exc:
        raise ScaffoldResourceError(
            f"could not locate packaged scaffold resources: {exc}"
        ) from exc
    if not root.is_dir():
        raise ScaffoldResourceError(
            "packaged scaffold resources are unavailable; reinstall "
            "practical-game-studio"
        )
    files = dict(_walk_files(root))
    required = {
        "AGENTS.md",
        ".studio/config.json",
        FRAMEWORK_MANIFEST_PATH,
        ".studio/workflow-catalog.json",
        ".studio/state/project.json",
        ".studio/reports/current-state.md",
    }
    missing = sorted(required - set(files))
    if missing:
        raise ScaffoldResourceError(
            "packaged scaffold is incomplete; missing: " + ", ".join(missing)
        )
    return {path: files[path] for path in sorted(files)}


def is_protected_path(relative: str) -> bool:
    """Return whether an existing project-specific file must be preserved."""

    return relative.startswith(PROTECTED_PREFIXES)


def is_replaceable_path(relative: str) -> bool:
    """Return whether force bootstrap may refresh an existing managed file."""

    return any(
        relative == prefix or relative.startswith(prefix)
        for prefix in REPLACEABLE_PREFIXES
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalized_manifest(content: bytes) -> bytes:
    try:
        value: Any = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return content
    if not isinstance(value, dict):
        return content
    normalized = dict(value)
    normalized["bootstrapped_at"] = None
    return (
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def framework_scaffold_differences(
    root: Path, packaged: dict[str, bytes] | None = None
) -> tuple[dict[str, str], ...]:
    """Compare canonical packaged framework files with root dogfood copies.

    Live state and generated reports are deliberately excluded from byte comparison:
    they are project-specific outputs. Their presence, schemas, relationships, and
    freshness are validated separately by project validation.
    """

    packaged = packaged or load_scaffold_files()
    differences: list[dict[str, str]] = []
    for relative, expected in packaged.items():
        if is_protected_path(relative):
            continue
        path = root / relative
        try:
            actual = path.read_bytes()
        except FileNotFoundError:
            differences.append(
                {
                    "path": relative,
                    "packaged_sha256": sha256_bytes(expected),
                    "framework_sha256": "missing",
                }
            )
            continue
        except OSError as exc:
            differences.append(
                {
                    "path": relative,
                    "packaged_sha256": sha256_bytes(expected),
                    "framework_sha256": f"unreadable:{exc}",
                }
            )
            continue
        if relative == FRAMEWORK_MANIFEST_PATH:
            expected = _normalized_manifest(expected)
            actual = _normalized_manifest(actual)
        if actual != expected:
            differences.append(
                {
                    "path": relative,
                    "packaged_sha256": sha256_bytes(expected),
                    "framework_sha256": sha256_bytes(actual),
                }
            )
    return tuple(sorted(differences, key=lambda item: item["path"]))
