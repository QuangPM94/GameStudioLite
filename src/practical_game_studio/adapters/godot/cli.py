"""The Godot command-line adapter.

This is the reference adapter: one engine must support the complete basic loop —
detect, run headless, test, build, export — without MCP or any editor
automation, so that the rest of the framework can be built against something
real rather than against a mock.

Every operation returns runs and artifacts. None of them concludes anything
about the game. `studio verify --level smoke` can establish that a process
started and did not immediately die; it cannot establish that the game is
playable, and it does not pretend to.
"""

from __future__ import annotations

from pathlib import Path

from ...execution import (
    ExecutionRecord,
    ExecutionRequest,
    complete_execution_record,
    create_execution_record,
    detect_revision,
    execute_process,
    platform_label,
)
from ..base import (
    CAPABILITY_RISK,
    AdapterOperationResult,
    BaseEngineAdapter,
    BuildOptions,
    CapabilityReport,
    DetectionResult,
    OperationAuthorization,
    ProbeResult,
    RunOptions,
    TestOptions,
)
from .commands import (
    build_command,
    export_command,
    run_command,
    test_command,
)
from .detector import (
    detect_godot_executable,
    detect_godot_project,
    get_godot_version,
    major_version,
)

#: A headless launch that has not exited by now is treated as "started and
#: stayed up", which is the only thing a smoke check can honestly conclude.
DEFAULT_RUN_TIMEOUT_SECONDS = 60.0
DEFAULT_TEST_TIMEOUT_SECONDS = 900.0
DEFAULT_BUILD_TIMEOUT_SECONDS = 1800.0


class GodotCliAdapter(BaseEngineAdapter):
    """Drive Godot through its command-line interface."""

    id = "godot-cli"
    display_name = "Godot (command line)"
    engine = "Godot"

    # --- detection ----------------------------------------------------------

    def detect(self, root: Path) -> DetectionResult:
        project = detect_godot_project(root)
        if not project.found:
            return DetectionResult(
                detected=False,
                detail="no project.godot found at the root or one level below",
            )
        indicators = [str(project.manifest.relative_to(root).as_posix())]
        if project.export_presets is not None:
            indicators.append(project.export_presets.relative_to(root).as_posix())
        if project.dotnet:
            indicators.append("C#/.NET project indicators")
        if project.test_framework:
            indicators.append(f"test framework: {project.test_framework}")
        return DetectionResult(
            detected=True,
            # A manifest at the root is a stronger signal than one found by
            # searching, so a repository containing several engine projects
            # resolves to the obvious one.
            confidence=90 if project.manifest.parent == root else 70,
            indicators=tuple(indicators),
            detail="Godot project manifest found",
            project_path=str(project.project_path),
        )

    # --- probing ------------------------------------------------------------

    def probe(self, root: Path) -> ProbeResult:
        project = detect_godot_project(root)
        executable = detect_godot_executable()
        version = get_godot_version(executable.path) if executable.found else None
        reports = self._capability_reports(project, executable, version)
        return ProbeResult(
            adapter_id=self.id,
            engine=self.engine,
            engine_version=version,
            executable=str(executable.path) if executable.found else None,
            capabilities=reports,
            limitations=self._limitations(project, executable, version),
        )

    def _capability_reports(
        self, project, executable, version
    ) -> tuple[CapabilityReport, ...]:
        def report(name: str, readiness: str, detail: str) -> CapabilityReport:
            return CapabilityReport(
                capability=name,
                readiness=readiness,
                detail=detail,
                risk=CAPABILITY_RISK.get(name, "low"),
            )

        if not project.found:
            return (report("RUN", "unavailable", "no Godot project was found"),)
        if not executable.found:
            # The project is real; only the engine is missing. Saying so is more
            # useful than a flat "unavailable" that hides which half is absent.
            reason = executable.detail
            return tuple(
                report(name, "unavailable", reason)
                for name in ("RUN", "HEADLESS", "TEST", "BUILD", "EXPORT")
            )

        reports = [
            report("RUN", "ready", f"engine at {executable.path}"),
            report("HEADLESS", "ready", "Godot supports --headless"),
            report("LOG_CAPTURE", "ready", "stdout and stderr are captured"),
        ]

        if project.test_framework:
            reports.append(
                report(
                    "TEST",
                    "ready",
                    f"{project.test_framework} was detected in the project",
                )
            )
        else:
            # No test framework is not a broken project. It is a project whose
            # test result is unknown, and verification levels decide whether
            # that is acceptable.
            reports.append(
                report(
                    "TEST",
                    "unavailable",
                    "no supported test framework (gdUnit4, GUT) was found",
                )
            )

        if project.export_preset_names:
            detail = "export presets: " + ", ".join(project.export_preset_names)
            reports.append(report("BUILD", "ready", detail))
            reports.append(report("EXPORT", "ready", detail))
        elif project.export_presets is not None:
            reports.append(
                report(
                    "BUILD",
                    "unknown",
                    "export_presets.cfg exists but no preset name could be read",
                )
            )
            reports.append(
                report(
                    "EXPORT",
                    "unknown",
                    "export_presets.cfg exists but no preset name could be read",
                )
            )
        else:
            reports.append(
                report("BUILD", "unavailable", "no export_presets.cfg in the project")
            )
            reports.append(
                report("EXPORT", "unavailable", "no export_presets.cfg in the project")
            )

        # These need editor or runtime automation the CLI does not offer. They
        # are reported rather than omitted so a reader can see they were
        # considered and found absent.
        for name in ("SCREENSHOT", "RUNTIME_INSPECT", "INPUT_INJECTION", "PROFILE"):
            reports.append(
                report(
                    name,
                    "unavailable",
                    "the Godot CLI cannot do this; an editor/MCP provider is required",
                )
            )
        if major_version(version) is None:
            reports.append(
                report(
                    "EDITOR_INSPECT",
                    "unknown",
                    "the engine version could not be read",
                )
            )
        return tuple(reports)

    def _limitations(self, project, executable, version) -> tuple[str, ...]:
        limitations: list[str] = []
        if project.found and not executable.found:
            limitations.append(executable.detail)
        if executable.found and version is None:
            limitations.append(
                "The engine did not report a version, so version-specific "
                "behaviour cannot be assumed."
            )
        if project.found and not project.test_framework:
            limitations.append(
                "No supported test framework was detected; a passing build says "
                "nothing about test coverage."
            )
        if project.dotnet:
            limitations.append(
                "This project has C#/.NET indicators; a .NET build may need the "
                "dotnet SDK in addition to the engine."
            )
        return tuple(limitations)

    # --- operations ---------------------------------------------------------

    def _execute(
        self,
        root: Path,
        *,
        action: str,
        command: tuple[str, ...],
        working_directory: Path,
        timeout_seconds: float | None,
        capture_log: bool,
        engine_version: str | None,
        authorization: OperationAuthorization,
        extra_limitations: tuple[str, ...] = (),
    ) -> ExecutionRecord:
        run_id = create_execution_record(
            root,
            action=action,
            command=command,
            adapter=self.id,
            working_directory=str(working_directory),
            revision=detect_revision(root),
            engine=self.engine,
            engine_version=engine_version,
            platform=platform_label(),
            risk_level=authorization.risk_level,
            authorization=authorization.authorization,
        )
        process = execute_process(
            ExecutionRequest(
                command=command,
                working_directory=working_directory,
                timeout_seconds=timeout_seconds,
            )
        )
        return complete_execution_record(
            root,
            run_id,
            process,
            capture_log=capture_log,
            extra_limitations=extra_limitations,
        )

    def run(self, root: Path, options: RunOptions) -> AdapterOperationResult:
        probe = self.probe(root)
        capability = "HEADLESS" if options.headless else "RUN"
        if not probe.supports(capability):
            return self._refuse(root, capability)

        project = detect_godot_project(root)
        command = run_command(probe.executable, project.project_path, options)
        timeout = options.timeout_seconds or DEFAULT_RUN_TIMEOUT_SECONDS
        record = self._execute(
            root,
            action="run",
            command=command,
            working_directory=project.project_path,
            timeout_seconds=timeout,
            capture_log=options.capture_log,
            engine_version=probe.engine_version,
            authorization=options.authorization,
            extra_limitations=(
                (
                    "The engine process was launched and observed; no gameplay, "
                    "input, or player experience was verified."
                ),
            ),
        )
        return AdapterOperationResult(
            record=record,
            status=record.status,
            detail=self._run_detail(record, timeout),
            limitations=tuple(record.process.limitations),
            artifacts=record.artifact_ids,
        )

    @staticmethod
    def _run_detail(record: ExecutionRecord, timeout: float) -> str:
        if record.process.outcome == "timeout":
            # A headless launch that has to be killed is the *expected* outcome
            # for a game with a main loop, and reads as success for a smoke
            # check while remaining honest that nothing else was established.
            return (
                f"The engine was still running after {timeout:g}s and was "
                "stopped. It started and did not exit early."
            )
        if record.status == "passed":
            return "The engine ran and exited cleanly."
        if record.status == "failed":
            return (
                f"The engine exited {record.process.exit_code}. See the captured log."
            )
        return record.process.error or "The engine run produced no usable result."

    def test(self, root: Path, options: TestOptions) -> AdapterOperationResult:
        probe = self.probe(root)
        project = detect_godot_project(root)
        if not probe.supports("TEST"):
            report = probe.capability("TEST")
            # No test framework is reported as `skipped`, not `failed`. A project
            # without tests has not been shown to be broken.
            return AdapterOperationResult(
                record=None,
                status="skipped",
                detail=report.detail if report else "no test framework was detected",
                limitations=(
                    "No tests were run, so nothing is known about test results.",
                ),
            )

        command = test_command(
            probe.executable, project.project_path, project.test_framework, options
        )
        record = self._execute(
            root,
            action="test",
            command=command,
            working_directory=project.project_path,
            timeout_seconds=options.timeout_seconds or DEFAULT_TEST_TIMEOUT_SECONDS,
            capture_log=True,
            engine_version=probe.engine_version,
            authorization=options.authorization,
            extra_limitations=(
                (
                    "Passing tests describe the code under test, not whether the "
                    "game is enjoyable or clear to a player."
                ),
            ),
        )
        return AdapterOperationResult(
            record=record,
            status=record.status,
            detail=(
                f"{project.test_framework} exited {record.process.exit_code}."
                if record.process.exit_code is not None
                else f"The test run ended: {record.process.outcome}."
            ),
            limitations=tuple(record.process.limitations),
            artifacts=record.artifact_ids,
        )

    def build(self, root: Path, options: BuildOptions) -> AdapterOperationResult:
        return self._build_or_export(root, options, action="build")

    def export(self, root: Path, options: BuildOptions) -> AdapterOperationResult:
        return self._build_or_export(root, options, action="export")

    def _build_or_export(
        self, root: Path, options: BuildOptions, *, action: str
    ) -> AdapterOperationResult:
        capability = "BUILD" if action == "build" else "EXPORT"
        probe = self.probe(root)
        if not probe.supports(capability):
            return self._refuse(root, capability)

        project = detect_godot_project(root)
        preset = options.target or (
            project.export_preset_names[0] if project.export_preset_names else None
        )
        if preset is None:
            return AdapterOperationResult(
                record=None,
                status="unsupported",
                detail="no export preset was named and none could be read",
                limitations=("No build was attempted.",),
            )
        if preset not in project.export_preset_names:
            # Godot would happily fail deep inside the export; naming the
            # mistake here is far more actionable.
            return AdapterOperationResult(
                record=None,
                status="unsupported",
                detail=(
                    f"export preset {preset!r} is not defined; available presets: "
                    + ", ".join(project.export_preset_names)
                ),
                limitations=("No build was attempted.",),
            )

        builder = build_command if action == "build" else export_command
        command, output_path = builder(
            probe.executable, project.project_path, preset, options
        )
        record = self._execute(
            root,
            action=action,
            command=command,
            working_directory=project.project_path,
            timeout_seconds=options.timeout_seconds or DEFAULT_BUILD_TIMEOUT_SECONDS,
            capture_log=True,
            engine_version=probe.engine_version,
            authorization=options.authorization,
            extra_limitations=(
                (
                    "A completed export is not a verified build; the packaged game "
                    "has not been launched."
                ),
            ),
        )
        return AdapterOperationResult(
            record=record,
            status=record.status,
            detail=(
                f"Export preset {preset!r} exited {record.process.exit_code}; "
                f"output: {output_path}"
            ),
            limitations=tuple(record.process.limitations),
            artifacts=record.artifact_ids,
        )
