"""Work packets: bounded autonomous work, not unrestricted project modification.

A WORK packet is a contract written *before* an agent starts. It states what to
change, which files may be touched, which may not, what must be true at the end,
and which commands prove it. The agent then works inside that boundary, and the
framework checks the boundary held.

The four rules below are the whole point, and each is enforced rather than
documented:

**An agent cannot widen its own scope.** `allowed_files` and `forbidden_files`
are set when the packet is created. Changing them is a mutation of the contract,
not of the work, and `studio work update` refuses it once work has started.

**An agent cannot mark work complete without verification.** Completion requires
a verification run that actually happened and actually passed. No verification,
no completion — there is no flag for "trust me".

**Failed verification keeps the packet incomplete.** A failing check moves the
packet to `failed`, never to `complete`, and the failure stays on the record.

**Out-of-scope changes fail verification.** The framework compares the files
that actually changed against the declared scope, so a packet that touched
something it promised not to cannot pass however green its tests are.
"""

from __future__ import annotations

import copy
import fnmatch
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .execution import ExecutionRequest, detect_revision, execute_process
from .models import MutationResult
from .state import StateObject, StateRepository
from .transaction import ReportRenderer, StateTransaction

WORK_ID_PATTERN = re.compile(r"^WORK-(\d{4,})$")
WORK_ID_WIDTH = 4

#: A packet's lifecycle. `blocked` is separate from `failed`: one means the work
#: cannot start, the other means it was attempted and did not hold up.
STATUSES = (
    "draft",
    "ready",
    "in-progress",
    "verifying",
    "complete",
    "failed",
    "blocked",
    "cancelled",
)

#: Statuses from which no further work happens without an explicit reopen.
TERMINAL_STATUSES = ("complete", "cancelled")

#: Risk classes, matching the execution-safety vocabulary so a packet's risk and
#: an operation's risk mean the same thing.
RISK_LEVELS = ("safe", "low", "medium", "high")

#: How long a single verification command may run before it is stopped.
VERIFICATION_TIMEOUT_SECONDS = 1800.0

#: Paths the packet lifecycle itself writes. `work start` and `work verify`
#: necessarily update the work document and re-render reports, so counting
#: those as the agent's changes would make every packet fail on the
#: framework's own bookkeeping. Every other path under `.studio` is still
#: checked, so a packet can still forbid an agent from hand-editing state.
LIFECYCLE_PATHS = (
    ".studio/state/work.json",
    ".studio/reports/*",
)


class WorkError(ValueError):
    """Base class for a rejected work-packet operation."""


class WorkInputError(WorkError):
    """A work packet was requested with values the caller must correct."""


class WorkNotFoundError(WorkError):
    """A referenced work packet does not exist."""


class ScopeViolationError(WorkError):
    """Work touched files its packet did not allow.

    Separate from a verification failure: the tests may all pass and the work
    still be outside its contract, which is exactly the failure mode bounded
    autonomy exists to catch.
    """


@dataclass(frozen=True, slots=True)
class WorkCreateRequest:
    """The contract a packet is created with."""

    goal: str
    reason: str
    #: Globs, relative to the project root. Empty means nothing may be changed,
    #: which is the safe default for a packet whose author forgot to say.
    allowed_files: Sequence[str] = ()
    forbidden_files: Sequence[str] = ()
    acceptance_criteria: Sequence[str] = ()
    verification_commands: Sequence[str] = ()
    critical_path_item: str | None = None
    dependencies: Sequence[str] = ()
    risk_level: str = "low"
    human_approval_required: bool = False


@dataclass(frozen=True, slots=True)
class ScopeReport:
    """Which changed files were inside the packet's contract, and which were not."""

    changed: tuple[str, ...]
    allowed: tuple[str, ...]
    violations: tuple[str, ...]
    #: True when the framework could not determine what changed at all.
    undetermined: bool = False
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Whether the scope held. An undetermined scope never counts as held."""

        return not self.violations and not self.undetermined

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": list(self.changed),
            "allowed": list(self.allowed),
            "violations": list(self.violations),
            "undetermined": self.undetermined,
            "detail": self.detail,
            "ok": self.ok,
        }


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """The result of running one packet's declared verification commands."""

    work_id: str
    passed: bool
    scope: ScopeReport
    command_results: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "passed": self.passed,
            "scope": self.scope.to_dict(),
            "commands": list(self.command_results),
            "detail": self.detail,
        }


def format_work_id(number: int) -> str:
    """Render a work number as its canonical `WORK-####` id."""

    return f"WORK-{number:0{WORK_ID_WIDTH}d}"


def allocate_work_id(packets: Sequence[StateObject]) -> str:
    """Return the next unused work id, never reusing a number."""

    highest = 0
    for packet in packets:
        match = WORK_ID_PATTERN.match(str(packet.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return format_work_id(highest + 1)


def find_work(state: StateObject, work_id: str) -> StateObject:
    """Return one packet or say which id was missing."""

    for packet in state.get("work", []):
        if packet.get("id") == work_id:
            return packet
    raise WorkNotFoundError(f"work packet {work_id} does not exist")


def _timestamp(clock: Any = None) -> str:
    now = clock() if clock else datetime.now(UTC)
    return now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: str | None, *, field_name: str, required: bool = True) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise WorkInputError(f"{field_name} is required")
        return None
    return str(value).strip()


def _unique(values: Sequence[str], *, field_name: str) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = _text(value, field_name=field_name)
        if text is not None and text not in cleaned:
            cleaned.append(text)
    return cleaned


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    """Whether a repository-relative path matches any glob in `patterns`."""

    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def changed_files(
    root: Path, since_revision: str | None
) -> tuple[tuple[str, ...], str]:
    """Return the files changed since a revision, and how that was determined.

    Uses git because it is the only source that can see a change the agent did
    not report. Asking the agent what it changed would make the scope check
    circular — the thing being checked would be supplying the evidence.
    """

    if since_revision is None:
        status = execute_process(
            ExecutionRequest(
                command=("git", "status", "--porcelain"),
                working_directory=root,
                timeout_seconds=60,
            )
        )
        if not status.ok:
            return (), "git could not report the working tree state"
        files = tuple(
            line[3:].strip().replace("\\", "/")
            for line in status.stdout.splitlines()
            if line.strip()
        )
        return files, "uncommitted changes in the working tree"

    diff = execute_process(
        ExecutionRequest(
            command=("git", "diff", "--name-only", since_revision),
            working_directory=root,
            timeout_seconds=60,
        )
    )
    if not diff.ok:
        return (), f"git could not diff against {since_revision}"
    tracked = tuple(
        line.strip().replace("\\", "/")
        for line in diff.stdout.splitlines()
        if line.strip()
    )
    untracked = execute_process(
        ExecutionRequest(
            command=("git", "ls-files", "--others", "--exclude-standard"),
            working_directory=root,
            timeout_seconds=60,
        )
    )
    extra = (
        tuple(
            line.strip().replace("\\", "/")
            for line in untracked.stdout.splitlines()
            if line.strip()
        )
        if untracked.ok
        else ()
    )
    return tuple(dict.fromkeys((*tracked, *extra))), f"changes since {since_revision}"


def check_scope(root: Path, packet: StateObject) -> ScopeReport:
    """Compare what actually changed against what the packet allowed."""

    files, detail = changed_files(root, packet.get("started_revision"))
    if not files and detail.startswith("git could not"):
        # Never report a held scope on a check that did not happen.
        return ScopeReport(
            changed=(),
            allowed=(),
            violations=(),
            undetermined=True,
            detail=detail,
        )

    files = tuple(path for path in files if not matches_any(path, LIFECYCLE_PATHS))
    allowed_patterns = packet.get("allowed_files") or []
    forbidden_patterns = packet.get("forbidden_files") or []
    allowed: list[str] = []
    violations: list[str] = []
    for path in files:
        if matches_any(path, forbidden_patterns):
            violations.append(f"{path} (explicitly forbidden)")
        elif matches_any(path, allowed_patterns):
            allowed.append(path)
        else:
            violations.append(f"{path} (not in allowed_files)")
    return ScopeReport(
        changed=tuple(files),
        allowed=tuple(allowed),
        violations=tuple(violations),
        detail=detail,
    )


class WorkService:
    """Create, advance, verify, and close work packets."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Any = None,
        report_renderer: ReportRenderer | None = None,
    ) -> None:
        self.root = root.resolve()
        self.repository = StateRepository(self.root)
        self.clock = clock
        self._report_renderer = report_renderer

    def _transaction(self, operation: str, *, dry_run: bool) -> StateTransaction:
        kwargs: dict[str, Any] = {"operation": operation, "dry_run": dry_run}
        if self._report_renderer is not None:
            kwargs["report_renderer"] = self._report_renderer
        return StateTransaction(self.root, **kwargs)

    def create(
        self, request: WorkCreateRequest, *, dry_run: bool = False
    ) -> MutationResult:
        """Write the contract a packet will be held to."""

        with self._transaction("work.create", dry_run=dry_run) as transaction:
            state = transaction.state
            timestamp = _timestamp(self.clock)
            packet = self._build(request, timestamp, state["work"]["work"])
            work = copy.deepcopy(state["work"])
            work["work"].append(packet)
            transaction.set_work(work)
            return transaction.commit(
                details={
                    "work": packet,
                    "work_id": packet["id"],
                    "recommended_next_command": f"studio work show {packet['id']}",
                }
            )

    def _build(
        self,
        request: WorkCreateRequest,
        timestamp: str,
        existing: Sequence[StateObject],
    ) -> StateObject:
        if request.risk_level not in RISK_LEVELS:
            raise WorkInputError(
                f"unsupported risk level {request.risk_level!r}; expected one of "
                + ", ".join(RISK_LEVELS)
            )
        acceptance = _unique(
            request.acceptance_criteria, field_name="acceptance criterion"
        )
        if not acceptance:
            # A packet with no acceptance criteria cannot be verified, so it
            # cannot be completed, so creating one would be creating a trap.
            raise WorkInputError(
                "a work packet needs at least one acceptance criterion; without "
                "one there is nothing that could make it complete"
            )
        allowed = _unique(request.allowed_files, field_name="allowed file pattern")
        if not allowed:
            raise WorkInputError(
                "a work packet needs at least one allowed_files pattern; an empty "
                "scope permits no change at all"
            )
        return {
            "id": allocate_work_id(existing),
            "goal": _text(request.goal, field_name="goal"),
            "reason": _text(request.reason, field_name="reason"),
            "critical_path_item": _text(
                request.critical_path_item,
                field_name="critical path item",
                required=False,
            ),
            "allowed_files": allowed,
            "forbidden_files": _unique(
                request.forbidden_files, field_name="forbidden file pattern"
            ),
            "dependencies": _unique(request.dependencies, field_name="dependency"),
            "acceptance_criteria": acceptance,
            "verification_commands": _unique(
                request.verification_commands, field_name="verification command"
            ),
            "risk_level": request.risk_level,
            "human_approval_required": bool(request.human_approval_required),
            "status": "ready",
            "result": None,
            "started_revision": None,
            "related_runs": [],
            "related_artifacts": [],
            "related_evidence": [],
            "verification_history": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def ready(self) -> tuple[StateObject, ...]:
        """Packets whose dependencies are all complete."""

        state = self.repository.load_one("work")
        by_id = {packet["id"]: packet for packet in state["work"]}
        return tuple(
            packet
            for packet in state["work"]
            if packet["status"] == "ready"
            and all(
                by_id.get(dependency, {}).get("status") == "complete"
                for dependency in packet["dependencies"]
            )
        )

    def start(self, work_id: str, *, dry_run: bool = False) -> MutationResult:
        """Begin work, pinning the revision the scope will be measured from."""

        with self._transaction("work.start", dry_run=dry_run) as transaction:
            state = transaction.state
            work = copy.deepcopy(state["work"])
            packet = find_work(work, work_id)
            if packet["status"] != "ready":
                raise WorkInputError(
                    f"{work_id} is {packet['status']}; only a ready packet can start"
                )
            unmet = [
                dependency
                for dependency in packet["dependencies"]
                if find_work(work, dependency)["status"] != "complete"
            ]
            if unmet:
                raise WorkInputError(
                    f"{work_id} depends on incomplete work: " + ", ".join(unmet)
                )
            packet["status"] = "in-progress"
            # Pinned now so the scope check later measures exactly this packet's
            # changes, not whatever was already lying around.
            packet["started_revision"] = detect_revision(self.root)
            packet["updated_at"] = _timestamp(self.clock)
            transaction.set_work(work)
            return transaction.commit(
                details={
                    "work": packet,
                    "work_id": work_id,
                    "allowed_files": packet["allowed_files"],
                    "forbidden_files": packet["forbidden_files"],
                    "recommended_next_command": f"studio work verify {work_id}",
                }
            )

    def verify(self, work_id: str) -> VerificationOutcome:
        """Run the packet's verification commands and check its scope.

        Read-only with respect to the packet: it reports what it found, and
        `record_verification` is what writes the outcome. Separating them keeps a
        dry check from advancing anything.
        """

        state = self.repository.load_one("work")
        packet = find_work(state, work_id)
        scope = check_scope(self.root, packet)
        results: list[dict[str, Any]] = []
        for command in packet["verification_commands"]:
            process = execute_process(
                ExecutionRequest(
                    command=tuple(command.split()),
                    working_directory=self.root,
                    timeout_seconds=VERIFICATION_TIMEOUT_SECONDS,
                )
            )
            results.append(
                {
                    "command": command,
                    "outcome": process.outcome,
                    "exit_code": process.exit_code,
                    "passed": process.ok,
                    "stderr_tail": process.stderr[-500:] if process.stderr else "",
                }
            )
        commands_passed = bool(results) and all(item["passed"] for item in results)
        return VerificationOutcome(
            work_id=work_id,
            passed=commands_passed and scope.ok,
            scope=scope,
            command_results=tuple(results),
            detail=self._verification_detail(packet, results, scope),
        )

    @staticmethod
    def _verification_detail(
        packet: StateObject, results: list[dict[str, Any]], scope: ScopeReport
    ) -> str:
        if not packet["verification_commands"]:
            return (
                "This packet declares no verification commands, so nothing "
                "could be proved. Completion requires at least one."
            )
        problems: list[str] = []
        failed = [item["command"] for item in results if not item["passed"]]
        if failed:
            problems.append("failing command(s): " + ", ".join(failed))
        if scope.undetermined:
            problems.append(f"scope could not be determined ({scope.detail})")
        elif scope.violations:
            problems.append("out-of-scope change(s): " + ", ".join(scope.violations))
        if problems:
            return "; ".join(problems)
        return (
            f"{len(results)} verification command(s) passed and every changed "
            "file was within the declared scope."
        )

    def record_verification(
        self, work_id: str, outcome: VerificationOutcome, *, dry_run: bool = False
    ) -> MutationResult:
        """Store a verification result, moving the packet to `failed` when it failed."""

        with self._transaction("work.verify", dry_run=dry_run) as transaction:
            state = transaction.state
            work = copy.deepcopy(state["work"])
            packet = find_work(work, work_id)
            timestamp = _timestamp(self.clock)
            packet["verification_history"].append(
                {
                    "passed": outcome.passed,
                    "detail": outcome.detail,
                    "scope_ok": outcome.scope.ok,
                    "verified_at": timestamp,
                }
            )
            # A failing check never leaves the packet looking startable again.
            packet["status"] = "verifying" if outcome.passed else "failed"
            packet["updated_at"] = timestamp
            transaction.set_work(work)
            return transaction.commit(
                details={
                    "work": packet,
                    "work_id": work_id,
                    "verification": outcome.to_dict(),
                    "recommended_next_command": (
                        f"studio work complete {work_id}"
                        if outcome.passed
                        else f"studio work show {work_id}"
                    ),
                }
            )

    def complete(
        self,
        work_id: str,
        *,
        result: str | None = None,
        evidence: Sequence[str] = (),
        dry_run: bool = False,
    ) -> MutationResult:
        """Close a packet as complete. Refused without a passing verification.

        There is no override. A packet that could be completed by asserting it
        was fine would make every other rule here decorative.
        """

        with self._transaction("work.complete", dry_run=dry_run) as transaction:
            state = transaction.state
            work = copy.deepcopy(state["work"])
            packet = find_work(work, work_id)
            history = packet["verification_history"]
            if not history:
                raise WorkInputError(
                    f"{work_id} has never been verified; run "
                    f"`studio work verify {work_id}` first"
                )
            if not history[-1]["passed"]:
                raise WorkInputError(
                    f"{work_id} last failed verification: {history[-1]['detail']}. "
                    "Fix the work and verify again; a packet cannot be completed "
                    "over a failing check."
                )
            known = {item["id"] for item in state["evidence"]["evidence"]}
            missing = sorted(set(evidence) - known)
            if missing:
                raise WorkInputError("unknown evidence: " + ", ".join(missing))

            packet["status"] = "complete"
            packet["result"] = _text(result, field_name="result", required=False) or (
                "Verification passed and every changed file was within scope."
            )
            packet["related_evidence"] = _unique(
                [*packet["related_evidence"], *evidence], field_name="evidence"
            )
            packet["updated_at"] = _timestamp(self.clock)
            transaction.set_work(work)
            return transaction.commit(details={"work": packet, "work_id": work_id})

    def fail(
        self, work_id: str, reason: str, *, dry_run: bool = False
    ) -> MutationResult:
        """Close a packet as failed, keeping why on the record."""

        with self._transaction("work.fail", dry_run=dry_run) as transaction:
            state = transaction.state
            work = copy.deepcopy(state["work"])
            packet = find_work(work, work_id)
            if packet["status"] in TERMINAL_STATUSES:
                raise WorkInputError(f"{work_id} is already {packet['status']}")
            packet["status"] = "failed"
            packet["result"] = _text(reason, field_name="reason")
            packet["updated_at"] = _timestamp(self.clock)
            transaction.set_work(work)
            return transaction.commit(details={"work": packet, "work_id": work_id})

    def attach(
        self,
        work_id: str,
        *,
        runs: Sequence[str] = (),
        artifacts: Sequence[str] = (),
        dry_run: bool = False,
    ) -> MutationResult:
        """Link the runs and artifacts produced while doing this work."""

        with self._transaction("work.attach", dry_run=dry_run) as transaction:
            state = transaction.state
            work = copy.deepcopy(state["work"])
            packet = find_work(work, work_id)
            known_runs = {item["id"] for item in state["runs"]["runs"]}
            known_artifacts = {item["id"] for item in state["artifacts"]["artifacts"]}
            missing = sorted(
                (set(runs) - known_runs) | (set(artifacts) - known_artifacts)
            )
            if missing:
                raise WorkInputError("unknown reference(s): " + ", ".join(missing))
            packet["related_runs"] = _unique(
                [*packet["related_runs"], *runs], field_name="run"
            )
            packet["related_artifacts"] = _unique(
                [*packet["related_artifacts"], *artifacts], field_name="artifact"
            )
            packet["updated_at"] = _timestamp(self.clock)
            transaction.set_work(work)
            return transaction.commit(details={"work": packet, "work_id": work_id})
