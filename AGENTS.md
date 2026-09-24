# Migration Agent Project Instructions

## Phase boundary

- Read `plannings/final/agent-platform-master-plan.md` and `docs/phase-status.md` before editing.
- Implement only the explicitly requested phase.
- Do not create speculative classes, directories, adapters, or infrastructure for later phases.
- Stop after the requested phase's quality gates and documentation updates.

## Architecture

- Dependencies point inward: CLI and infrastructure may depend on application/domain code; the domain never depends on them.
- Domain modules must not import Typer, the OpenAI Agents SDK, filesystem adapters, command runners, or persistence implementations.
- Framework-specific behavior belongs in adapters, never in core application services.
- All public boundaries use typed models.
- Mechanical work is deterministic; model output is untrusted input.

## Safety

- Treat every selected source repository as read-only.
- Keep source, staging, and run/artifact roots distinct and reject overlapping unsafe paths.
- Require approval before migration changes or risky commands, not before ordinary reports or state records.
- Never execute raw model-generated shell commands.
- Never read, store, log, or print secrets.
- Tests must not require network access or `OPENAI_API_KEY`.
- Fail closed on unsupported or uncertain constructs.

## Portability and quality

- Support Python 3.12+ on Windows and Linux.
- Normalize persisted repository-relative paths to POSIX form.
- Preserve deterministic ordering in machine-readable artifacts.
- Explain architectural decisions in `docs/`, not with excessive inline comments.
- Add focused tests for every behavior introduced in the current phase.

## Required commands

Run all of these before completing a phase:

```text
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run migration-agent doctor
```

