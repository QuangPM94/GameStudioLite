# Reference Adaptation Record

Recorded before implementation on 2026-07-27.

The read-only architectural reference is [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios), MIT licensed.

PGS adapts these patterns:

- responsibility, authority, evidence, and escalation boundaries for roles;
- a machine-readable phase/workflow catalog;
- guided onboarding that detects current project stage;
- an explicit distinction between prototypes and vertical slices;
- selectable review intensity;
- persistent project/session state;
- structured templates with known consumers;
- validation before completion;
- issue, milestone, and critical-path workflows.

PGS intentionally differs by using five roles rather than a studio hierarchy, twelve playbooks rather than dozens of skills, root `AGENTS.md` rather than Claude-specific hooks, canonical JSON with generated reports, practical autonomy instead of per-write approval, optional ADRs, and no mandatory GDD-per-system or production architecture before a prototype.
