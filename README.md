# Migration Agent (`agent` / `migration-agent`)

The **Migration Agent** is a controlled, evidence-based code migration workbench designed to safely and deterministically transform legacy web applications (Ember.js, AngularJS) into modern Angular (17+ through 21+ Standalone with Signals).

The platform enforces **strict security invariants**, treating source code as strictly read-only, confining all mutations to isolated staging sandboxes, using cryptographic approval bindings (RFC 8785 canonical digests), and executing changes via the **ADR-8 4-step controlled apply protocol** with verified byte-level rollbacks.

---

## Key Features

- **Multi-Framework Detection & Migration**: Converts legacy Ember Classic and AngularJS Directives, Controllers, Templates, and Services to modern Angular Standalone components with Angular Signals, `@if`/`@for` control flow, and Bootstrap 5 utilities.
- **Unified Migration Pipeline (`agent migrate`)**: Preflight, configured-provider planning, isolated staging, and bounded self-repair/validation. Stops for human review of the exact ChangeSet; approved bytes are applied through the shared guarded service.
- **Actionable Diagnostic Self-Repair**: Autonomous resolution of TypeScript compilation errors (`TS2304` auto-imports), Angular signal invocations (`TS2551`), and Jasmine `TestBed` mocking failures (`NullInjectorError`).
- **Full-Stack Dependency Discovery**: Read-only discovery of frontend HTTP invocations, backend API routes (FastAPI, Flask, Express), and database schemas (SQL DDL).
- **Common Control Center GUI**: Offline Angular 21 project explorer, evidence-based progress, mobile navigation drawer, optional typed Git-owned work definitions and guarded workflow requests. Human approval remains separate in the trusted terminal.
- **Durable Governance & Curated Knowledge**: Git-native `.agent/` architecture documentation, Architectural Decision Records (`agent decision`), challenge/solution lifecycles (`agent learning`), and contextual Q&A (`agent ask`).
- **Semantic Evaluation Benchmarking (`agent eval --semantic`)**: Structural proxy metrics for syntax, spec completeness, and control flow fidelity; these metrics do not execute a compiler or test suite.

---

## Documentation

Full documentation is organized by persona in the [`docs/`](docs/) directory:

- 🧭 **[Documentation Hub & Index](docs/index.md)**: Master navigation map for project owners, architects, and developers.
- 📖 **[User Guide & CLI Reference](docs/user-guide.md)**: Step-by-step practical guide covering all commands, flags, and workflows.
- ⚡ **[Capabilities & Platform Matrix](docs/capabilities.md)**: Detailed framework detection rules, target standards, and self-repair engine specifications.
- 🏛️ **[System Architecture](docs/architecture.md)**: Hexagonal architecture, ports/adapters, storage topology, and cryptographic security protocols.
- 🛡️ **[Threat Model & Security Invariants](docs/threat-model.md)**: 28 security invariants, isolation boundaries, and fail-closed safety defenses.
- 📝 **[Learning Log](docs/learning-log.md)**: Chronological architectural decisions and engineering insights across all phases.
- ✅ **[Phase Verification Status](docs/phase-status.md)**: Current and historical quality gates and remaining acceptance evidence.
- 🗺️ **[Roadmap](docs/roadmap.md)**: Milestone progression across Phases 0 through 15.

---

## Quickstart

### Prerequisites
- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) package manager
- Git

### Installation
```bash
git clone <repository-url> migration-agent
cd migration-agent
uv sync --all-groups
```

### Health Check
```bash
uv run agent doctor
```

### Phase 16 MCP server

```bash
uv run agent mcp serve --project-root /path/to/source --state-dir /path/to/separate/state
```

The server provides fifteen typed tools for inspection, grounded proposals, durable operations, staging, validation, review requests, and guarded apply. Obtain the opaque project ID from `migration_inventory`; paging fields retrieve large file lists and plan step lists. Source, state, and staging roots must be distinct.

Host proposals, shared headless approval/apply, and preview-first client setup are implemented. Actual Antigravity/Codex compatibility is pending measured verification. See the current [governed migration workflow](docs/migration-workflow.md), [operation guide](docs/phase-16-client-setup.md) and [compatibility evidence](docs/phase-16-smoke-checklists.md).

### Run a Safe Migration Preview (Dry-Run)
```bash
uv run agent migrate /path/to/legacy-repo --dry-run
```

### Execute End-to-End Migration
```bash
uv run agent migrate /path/to/legacy-repo
```

The pipeline stops before source apply. Complete the separate human review and
approval steps in the [workflow guide](docs/phase-16-client-setup.md). Full GUI
development and acceptance belong to a separate phase.

---

## Quality Gates

To verify environment health, run the standard quality gates:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run migration-agent doctor
```

## Phase 16 host integration

Antigravity/Codex can supply reasoning through eighteen typed stdio tools while standalone CLI analysis/planning uses the configured provider. Both surfaces share external staging, validation, human exact ChangeSet approval, and guarded apply. Preview client configuration with `agent mcp setup --client codex --project-root <source>` (or `--client antigravity`). See [setup and workflow](docs/phase-16-client-setup.md) and [acceptance evidence](docs/phase-16-smoke-checklists.md). Real IDE acceptance remains pending; this phase includes no GUI implementation.

## Native validation on Windows

Trusted Windows projects can validate without Docker, WSL or Linux using explicit
`AGENT_VALIDATION_MODE=native`, externally provisioned tools/dependencies, and
human `agent validation authorize` consent. Source apply still requires separate
exact approval. Unconfigured projects remain restricted; container mode is optional
and never falls back to native. See [native operations](docs/native-validation.md).

## Application browser UI/UX validation

Production approval now also requires real browser screenshots and complete AI
UI/UX review across the declared responsive states, followed by optional E2E last.
Host review, source comparison and bounded repair share the existing guarded workflow.
Standalone OpenAI/Gemini visual review is available through an explicit trusted
launcher export opt-in, with fixed destinations and bounded evidence/code payloads.
See [browser operations](docs/browser-ui-ux-validation.md).

## Common Control Center

Launch `uv run agent ui /path/to/project` using your workflow's external state and
staging roots. The browser offers hierarchical dashboards, search/attention,
checks/artifacts/decisions, runs, health and cited recorded-fact questions.
Optionally define foundation/module groups and metadata in
[.agent/project-work.json](docs/project-work.md); declarations never substitute
for verified workflow evidence. Detailed review and human approval retain their
IDE/CLI handoffs. See [operations](docs/control-center.md),
[Angular development](ui/control-center/README.md) and
[verification](plannings/control-center-implementation-report.md).

## Project Settings

Control Center → **Settings** manages approved provider/model profiles, personal choices,
environment paths, validation configuration and next-launch directories. Shared settings require
exact owner approval; routine personal choices stay within signed constraints. `agent config`
provides equivalent CLI inspection, proposals, checks and recovery. See
[configuration operations](docs/project-configuration.md) and
[implementation evidence](plannings/agent-configuration-management-implementation-report.md).
Settings saves never start migration workflows. Final target directories remain planning only.
