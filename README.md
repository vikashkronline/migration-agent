# Migration Agent

Migration Agent is a learning-oriented foundation for controlled, evidence-based code
migrations. The long-term goal is to discover a codebase, analyze it, plan a migration,
require human approval, transform only an isolated staging workspace, validate the result,
and return an auditable patch.

## Current scope

Phases 0 and 1 are implemented. The project provides:

- a Python 3.12+ package managed with `uv`;
- typed environment configuration;
- one framework-neutral migration request model;
- a machine-readable `migration-agent doctor` command; and
- deterministic, read-only web-project inventory with evidence-based Ember Classic and
  Angular detection;
- stable JSON and concise Markdown inventory reports; and
- offline tests plus linting, formatting, and static-type checks.

There is no LLM call, agent runtime, migration plan, transformation, command execution, or
run persistence yet.

## Setup

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), then run:

```powershell
uv sync --all-groups
```

Copy `.env.example` to `.env` only when local configuration is needed. Phase 0 does not
require `OPENAI_API_KEY`, and `.env` is ignored by Git.

## Commands

```powershell
uv run migration-agent doctor
uv run migration-agent inventory PATH --output OUTPUT_DIRECTORY
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

`doctor` emits a single JSON object. An unset `MIGRATION_AGENT_MODEL` is informational in
Phase 0 and does not make the command fail.

`inventory` reads a selected repository without following symlinks or junctions. The output
directory must not overlap the source repository. It writes `inventory.json` and
`inventory.md`; excluded secrets and unsafe files are reported only as aggregate counts.

## Two different agents

Codex is the development assistant used to build this repository. The future runtime
migration agent is application code that will use an API through a narrow port beginning
in Phase 2. Codex access does not configure or authenticate that future runtime agent.

## Development approach

Work proceeds one phase at a time according to
`plannings/final/agent-platform-master-plan.md`. Read `docs/phase-status.md` before starting
work and stop at the active phase boundary. The Phase 1 security assumptions and residual
risks are recorded in `docs/threat-model.md`.
