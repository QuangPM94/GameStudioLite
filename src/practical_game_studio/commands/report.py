"""`studio report` — regenerate Markdown reports from canonical JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..reporting import generate_reports
from ._shared import _add_root_argument


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register `studio report`."""

    report_parser = subparsers.add_parser(
        "report", help="generate Markdown reports from canonical JSON"
    )
    _add_root_argument(report_parser)


def run(args: argparse.Namespace, root: Path) -> int:
    """Regenerate every managed report and list what was written."""

    generated = generate_reports(root)
    print(f"Generated {len(generated)} report(s):")
    for path in generated:
        print(f"- {path.relative_to(root).as_posix()}")
    return 0
