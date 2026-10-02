# Migration Agent (`agent` / `migration-agent`)

The **Migration Agent** is a controlled, evidence-based code migration workbench designed to safely and deterministically transform legacy web applications (Ember.js, AngularJS) into modern Angular (17+ through 21+ Standalone with Signals).

The platform enforces **strict security invariants**, treating source code as strictly read-only, confining all mutations to isolated staging sandboxes, using cryptographic approval bindings (RFC 8785 canonical digests), and executing changes via the **ADR-8 4-step controlled apply protocol** with verified byte-level rollbacks.

---

## Key Features

- **Multi-Framework Detection & Migration**: Converts legacy Ember Classic and AngularJS Directives, Controllers, Templates, and Services to modern Angular Standalone components with Angular Signals, `@if`/`@for` control flow, and Bootstrap 5 utilities.
- **Unified End-to-End Pipeline (`agent migrate`)**: Single command execution orchestrating preflight checks, plan generation, interactive/automated Mode B sign-off, staging execution, validation gates with bounded self-repair, and verified patch application.
- **Actionable Diagnostic Self-Repair**: Autonomous resolution of TypeScript compilation errors (`TS2304` auto-imports), Angular signal invocations (`TS2551`), and Jasmine `TestBed` mocking failures (`NullInjectorError`).
- **Full-Stack Dependency Discovery**: Read-only discovery of frontend HTTP invocations, backend API routes (FastAPI, Flask, Express), and database schemas (SQL DDL).
- **Local Control Center Web GUI (`agent ui`)**: Browser-based dashboard on loopback (`http://127.0.0.1:8080`) for visual DAG inspection, live diff reviews, and interactive approvals.
- **Durable Governance & Curated Knowledge**: Git-native `.agent/` architecture documentation, Architectural Decision Records (`agent decision`), challenge/solution lifecycles (`agent learning`), and contextual Q&A (`agent ask`).
- **Semantic Evaluation Benchmarking (`agent eval --semantic`)**: Automated verification of compilation pass rates, Jasmine test completeness, and Angular 17+ control flow fidelity.

---

## Documentation

Full documentation is organized by persona in the [`docs/`](docs/) directory:

- 🧭 **[Documentation Hub & Index](docs/index.md)**: Master navigation map for project owners, architects, and developers.
- 📖 **[User Guide & CLI Reference](docs/user-guide.md)**: Step-by-step practical guide covering all commands, flags, and workflows.
- ⚡ **[Capabilities & Platform Matrix](docs/capabilities.md)**: Detailed framework detection rules, target standards, and self-repair engine specifications.
- 🏛️ **[System Architecture](docs/architecture.md)**: Hexagonal architecture, ports/adapters, storage topology, and cryptographic security protocols.
- 🛡️ **[Threat Model & Security Invariants](docs/threat-model.md)**: 28 security invariants, isolation boundaries, and fail-closed safety defenses.
- 📝 **[Learning Log](docs/learning-log.md)**: Chronological architectural decisions and engineering insights across all phases.
- ✅ **[Phase Verification Status](docs/phase-status.md)**: Quality gate results and test audit logs (345+ tests, 100% green).
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

### Run a Safe Migration Preview (Dry-Run)
```bash
uv run agent migrate /path/to/legacy-repo --dry-run
```

### Execute End-to-End Migration
```bash
uv run agent migrate /path/to/legacy-repo
```

### Launch Web Control Center UI
```bash
uv run agent ui /path/to/legacy-repo
```

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
