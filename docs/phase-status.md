# Phase Status

## Phase 0 — Complete

Scope: initialize the Python project, typed configuration, one domain model, the `doctor`
command, project guidance, and offline quality tooling.

Completed on 2026-09-17 using `uv` 0.12.15 and an isolated CPython 3.12.14
environment. The dependency lock resolved 26 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 26 packages; checked 26 packages.

uv run pytest
7 passed in 0.28s

uv run ruff check .
All checks passed.

uv run ruff format --check .
16 files already formatted.

uv run mypy src
Success: no issues found in 5 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok".
```

The Windows host required the final console-script gate to be launched through
`cmd.exe` because PowerShell denied direct execution of the generated launcher. The
command itself and its result were unchanged. This was a host execution-policy behavior,
not an application failure.

## Phase 1 — Complete

Scope: deterministic read-only repository discovery, typed inventory contracts,
filesystem and framework ports, Ember Classic and Angular evidence adapters, stable JSON
and Markdown reports, an initial threat model, and a synthetic Ember Classic fixture.

Completed on 2026-09-17. The required evidence is:

```text
uv sync --all-groups
Resolved 26 packages; checked 26 packages.

uv run pytest
22 passed in 0.70s

uv run ruff check .
All checks passed.

uv run ruff format --check .
31 files already formatted.

uv run mypy src
Success: no issues found in 15 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok".
```

An inventory smoke run against the checked-in Ember Classic fixture produced six eligible
files, three dependencies, one `ember-classic` fingerprint with four evidence items, no
issues, and both report formats. The original fixture remained unchanged. Tests cover
unknown-framework behavior, Angular evidence, package boundaries, ignored and unsafe
files, binary and size limits, a real symlink escape, output-root overlap, deterministic
serialization, malformed manifests, and secret-name nondisclosure.

## Phase 2 — Complete

Scope: provider-neutral read-only analysis agent behind application-owned `AgentRuntimePort`,
Google Gemini runtime adapter via official `google-genai` SDK as default provider, OpenAI
Agents SDK adapter as parallel provider, bounded read-only repository tools, Pydantic structured
outputs, post-generation deterministic evidence validation, deterministic offline fake runtime,
schema-versioned JSON and Markdown analysis report writer, and `agent analyze` / `migration-agent analyze`
CLI commands with dry-run default.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency
lock resolved 69 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 69 packages.

uv run pytest
40 passed, 2 skipped in 4.32s

uv run ruff check .
All checks passed!

uv run ruff format --check .
57 files already formatted.

uv run mypy src
Success: no issues found in 22 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

An analysis smoke run against the checked-in Ember Classic fixture produced three representative
findings (two component patterns with template/test evidence and one dependency finding),
100% verified evidence paths, zero file mutations, and both `analysis.json` and `analysis.md`
reports. Tests cover domain immutability, post-generation evidence audit, hallucinated path
containment, bounded tool queries and character caps, provider neutrality, fake runtime behavior,
CLI options (`--provider`, `--model`, `--fake-runtime`), and strict layer boundaries.

## Phase 3 — Complete

Scope: typed migration planning, rule-based DAG validator with cycle detection, ADR-1 4-tier
storage foundation (Git governance in `.agent/`, SQLite operational state in `checkpoints.db`,
JSONL append-only audit stream in `audit.jsonl`), RFC 8785 canonical JSON metadata hashing,
ADR-2 cryptographic approval binding (`ApprovalSignature`) with automatic approval invalidation
upon plan or policy tampering, and `agent plan` CLI commands (`create`, `show`, `approve`, `reject`).

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency
lock resolved 69 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
76 passed, 2 skipped in 7.37s

uv run ruff check .
All checks passed!

uv run ruff format --check .
72 files already formatted.

uv run mypy src
Success: no issues found in 30 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

A planning smoke run against the checked-in Ember Classic fixture produced structured migration
steps (package dependency setup and component conversion), verified DAG dependencies, exported
durable Git governance files (`.agent/manifest.json`, `.agent/policy.json`, `.agent/plans/<plan_id>.json`),
recorded canonical SQLite operational run state and checkpoints, appended to `audit.jsonl`, and validated
that any plan mutation immediately invalidates approval signatures.

## Phase 4 — Complete

Scope: isolated staging transformations, intermediate component representation, presentational
Ember Classic extraction to modern Angular Standalone rendering conforming to Angular 17+ standards,
typed `ChangeSet` model with POSIX path normalization, file modes (0644/0755), per-file SHA-256 byte
digests and RFC 8785 canonical metadata digest, working tree fingerprinting for drift detection,
isolated staging workspace management with symlink defenses and path confinement (`WorkspacePort`
and `LocalWorkspaceAdapter`), ADR-8 4-step controlled apply protocol with verified rollback and
operator-intervention `RecoveryRequired` double-fault state, and CLI commands `agent preview`,
`agent stage`, and `agent apply`.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency
lock resolved 69 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
108 passed, 2 skipped in 8.01s

uv run ruff check .
All checks passed!

uv run ruff format --check .
83 files already formatted.

uv run mypy src
Success: no issues found in 36 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

A transformation smoke run against the checked-in Ember Classic fixture (`user-card.js` and `user-card.hbs`)
produced four generated Angular Standalone artifacts (`user-card.component.ts` with `standalone: true`,
`OnPush`, signals, and typed inputs/state; `user-card.component.html` with modern `@if` control flow and
Bootstrap 5 utility classes; `user-card.component.scss` with component scoping; and `user-card.component.spec.ts`
with `TestBed` component testing). Transformations pass preflight verification and generate backup diff
snapshots. Any drift in the target repository aborts apply with `BaseChanged`. Controlled apply failure triggers
verified rollback, and rollback failure cleanly transitions to `RecoveryRequired`.

## Phase 5 — Complete

Scope: allowlisted validation profiles owned by target framework adapters (`LINT`, `TYPECHECK`, `TEST`, `BUILD`),
subprocess confinement via `CommandRunnerPort` (`SubprocessCommandRunner` & `FakeCommandRunner`) with strictly allowlisted
executables (`git`, `node`, `npm`, `npx`, `ng`, `tsc`, `pytest`, `python`, `uv`), `shell=False`, environment sanitization
dropping all sensitive API keys/credentials, bounded timeouts and output truncation (64KB cap with full output SHA-256 digest),
bounded self-repair loop under Invariant 26 (max budget of 3 attempts, citing validation diagnostics, generating fresh
`ChangeSet`s with fresh RFC 8785 digests, terminating on repeated identical failure or exhausted budget, aborting with
`DISALLOWED` on unapproved scope expansion), comprehensive `MigrationRunReport` domain entity with SQLite persistence
and Markdown generation, and CLI commands `agent validate` and `agent run`.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency lock resolved 69 packages.
The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
138 passed, 2 skipped in 15.31s

uv run ruff check .
All checks passed!

uv run ruff format --check .
97 files already formatted.

uv run mypy src
Success: no issues found in 40 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

A validation smoke run against the checked-in Ember Classic fixture (`fixtures/ember-classic-mini`) executed end-to-end:
staged the approved plan, ran all 4 validation checks (`LINT`, `TYPECHECK`, `TEST`, `BUILD`), produced an immutable
`MigrationRunReport` stored canonically in SQLite `run_reports` and mirrored to `run_report_<run_id>.json` and `.md`,
leaving the original repository fixture completely untouched.

## Phase 6 — Complete

Scope: Resumable operational state machine across process crashes via `RunRecord` in `SqliteCheckpointStore` (`runs` table),
audit event journal mirroring append-only to `audit.jsonl` with deterministic secret redaction and SHA-256 digested truncations
for payloads > 512 bytes via `RedactionPolicy`, chronological audit log verification (`verify_audit_log`), resumable execution
service (`ResumableExecutionService`) skipping workspace staging on resumption when already staged and continuing self-repair
with remaining attempt budgets, repeatable offline evaluation benchmark harness (`EvaluationService`) with ground-truth
scoring (`EvaluationBenchmark`, `EvaluationMetric`, `EvaluationResult`) calculating precision, recall, and F1, and CLI commands
`agent run list`, `agent run show <run_id>`, `agent run resume <run_id>`, and `agent eval [fixture_path]`.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency lock resolved 69 packages.
The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
158 passed, 2 skipped in 12.33s

uv run ruff check .
All checks passed!

uv run ruff format --check .
102 files already formatted.

uv run mypy src
Success: no issues found in 45 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

An evaluation run against `tests/fixtures/ember-classic-mini` via `migration-agent eval` scored 1.0 precision, 1.0 recall, 1.0 F1 score,
and passed offline verification in 14ms without network or live API keys.

## Phase 7 — Complete

Scope: Framework adapter capability negotiation (`FrameworkCapability`, `FrameworkCapabilities`, `NegotiationResult`),
second reference migration pair (`AngularJsDirectiveAdapter`, `AngularJsDirectiveExtractor`, `AngularStandaloneComponentRenderer`),
reusable adapter contract test suite (`test_framework_adapter_contract.py`) verified against all adapters,
synthetic fixture (`tests/fixtures/angularjs-directive-mini`), complete decoupling of core services (`TransformationService`)
ensuring 0% framework-specific conditionals, and offline evaluation benchmark scoring 1.0 F1 across both fixtures.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency lock resolved 69 packages.
The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages in 2ms; checked 68 packages in 14ms.

uv run pytest
188 passed, 2 skipped in 14.95s

uv run ruff check .
All checks passed!

uv run ruff format --check .
106 files already formatted.

uv run mypy src
Success: no issues found in 46 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

Smoke runs across both reference fixtures executed successfully:
1. `tests/fixtures/ember-classic-mini`: `migration-agent inventory` detected `ember-classic` with 1.0 confidence; `migration-agent eval` achieved 1.0 precision, 1.0 recall, and 1.0 F1 score in 312ms.
2. `tests/fixtures/angularjs-directive-mini`: `migration-agent inventory` detected `angularjs-directive` with 1.0 confidence; `migration-agent eval` achieved 1.0 precision, 1.0 recall, and 1.0 F1 score in 109ms.
Contract tests verify that all adapters conform to the `FrameworkAdapter` protocol, capability declarations, detection thresholds, and transformation boundaries.

## Phase 8 — Complete

Scope: Specialist subagents driven by evaluation evidence (ADR-6).
- Candidate specialist roles: Inventory Interpreter, Migration Analyst, Plan Critic, Repair Diagnostician.
- Typed inter-agent request/response contracts (`SpecialistRole`, `InventoryInterpretationRequest`, `InventoryInterpretation`, `MigrationAnalystRequest`, `MigrationAnalysisOutput`, `PlanCriticRequest`, `PlanCritique`, `RepairDiagnosticianRequest`, `RepairDiagnosis`, `SpecialistEvaluationMetric`).
- Centralized mutation authority: subagents remain strictly read-only; mutations are generated only via deterministic aggregators (`DeterministicPlanCriticAggregator`, `DeterministicRepairDiagnosticianAggregator`) and validated by the core engine.
- Global turn and cost budgets with fail-closed enforcement (`BudgetLimit`, `BudgetTracker`, `BudgetExhaustedError`, `SpecialistCoordinator`).
- Comparative evaluation harness measuring performance/quality with vs. without specialist subagents on reference fixtures.
- CLI flags: `--critic / --no-critic` on `plan create`, `--with-specialists` on `eval`.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
214 passed, 2 skipped in 17.50s

uv run ruff check .
All checks passed!

uv run ruff format --check .
116 files already formatted.

uv run mypy src
Success: no issues found in 49 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

Comparative benchmark runs:
1. `migration-agent eval tests/fixtures/ember-classic-mini --with-specialists`:
   Baseline F1: 1.0, Specialist F1: 1.0, Plan Critic Score: 0.95, Turns: 2, Cost: $0.001, Improvement detected: True.
2. Plan creation with critic: `migration-agent plan create tests/fixtures/ember-classic-mini --fake-runtime --critic` successfully integrated Plan Critic findings into validation warnings without mutating DAG topology.
3. Repair loop with Diagnostician: Diagnostician invoked on validation failure, out-of-scope patches deterministically rejected per Invariant 26, in-scope patches correctly resolved failures.

## Phase 9 — Complete

Scope: Expansion to Full-Stack Migration Domains & cross-domain dependency graphs.
- Typed domain contracts: `MigrationDomain` (`FRONTEND`, `BACKEND_API`, `DATABASE_SCHEMA`, `INFRASTRUCTURE`), `DependencyRelation` (`INVOKES_API`, `CALLS_SERVICE`, `QUERIES_DB`, `DEFINES_SCHEMA`, `CONFIGURES`, `DEPENDS_ON`), `CrossDomainNode`, `CrossDomainEdge`, `CrossDomainDependencyGraph`, `ImpactReport`, and `FullStackInventory`.
- Cross-domain dependency graph modeling: directed graph linking `UI -> API -> Service -> DB`, cycle detection, topological sorting, ripple/impact analysis (`analyze_impact`), and domain-partitioned Mermaid flowchart generation (`to_mermaid`).
- Read-only discovery adapters: `FrontendDomainAdapter` (components and outbound API calls), `BackendApiAdapter` (FastAPI and Express route handlers and database queries), `SqlDatabaseAdapter` (static DDL parsing and strict read-only SQLite inspection with zero mutations), and `InfrastructureAdapter` (Dockerfile and docker-compose services).
- Cross-domain dependency linker: `CrossDomainLinker` deterministically synthesizing cross-layer edges connecting UI components to backend endpoints, backend queries to database tables, and compose services to application layers.
- Full-stack reporting: `FullStackReportWriter` generating `fullstack_inventory.json`, `dependency_graph.mermaid`, and `fullstack_inventory.md` with source repository overlap rejection.
- Synthetic full-stack test fixture: `tests/fixtures/fullstack-ecommerce-mini` incorporating Angular Standalone frontend, Express backend, SQL schema, and docker-compose infrastructure.
- CLI commands: `migration-agent graph PATH` (alias: `migration-agent fullstack PATH`) supporting `--format [json|mermaid|summary]`, `--mermaid`, `--output-dir`, and `--impact-of <node_id>`.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency lock resolved 69 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
243 passed, 2 skipped in 13.92s

uv run ruff check .
All checks passed!

uv run ruff format --check .
126 files already formatted.

uv run mypy src
Success: no issues found in 54 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

A full-stack smoke run against `tests/fixtures/fullstack-ecommerce-mini` executed end-to-end:
1. `migration-agent graph tests/fixtures/fullstack-ecommerce-mini --mermaid` generated a verified Mermaid flowchart organized into 4 domain subgraphs (`Frontend`, `Backend API`, `Database Schema`, `Infrastructure`).
2. `migration-agent graph tests/fixtures/fullstack-ecommerce-mini --impact-of db:users --format summary` identified 7 dependent components across 4 domains (`frontend`, `backend_api`, `database_schema`, `infrastructure`).
3. Database inspection verified strict read-only guarantees (SQLite opened via URI `mode=ro`, DDL statically parsed, zero write/schema mutations executed).

## Phase 10 — Complete

Scope: Local Control Center GUI, loopback Control API server, and distribution packaging pipeline (ADR-5, ADR-9).
- Local Control Center Web GUI:
  - Angular 21 LTS Standalone UI architecture adhering to modern standards (`standalone: true`, `ChangeDetectionStrategy.OnPush`, `@if` / `@for track`, `inject()`, Signals, Bootstrap 5.3 utilities, theme toggle with native dark mode).
  - Bundled self-contained web assets in `src/migration_agent/ui/static/` (`index.html`, `styles.css`, `app.js`) supporting offline execution with strict Mermaid.js diagram visualization, side-by-side diff review with syntax highlighting, and interactive plan approval signing with canonical RFC 8785 digests.
  - Angular Standalone TypeScript source suite in `ui/control-center/` (`AppComponent`, `RunListComponent`, `DiffViewerComponent`, `PlanDetailComponent`, `GraphViewerComponent`, `ControlApiService`, `EventSocketService`).
- Loopback Control API Server (`127.0.0.1`):
  - Standard library `ThreadingHTTPServer` bound strictly to loopback (`127.0.0.1` or `localhost`); any non-loopback bind address is rejected with `PermissionError`.
  - Cryptographically generated session token per launch (`secrets.token_urlsafe(32)`), authenticated via `X-Session-Token`, Bearer authorization header, cookie, or query parameter.
  - Strict browser Origin / Referer validation enforcing exact match with loopback host and listening port; external origins are rejected with 403 Forbidden.
  - CSRF token validation (`X-CSRF-Token`) required on all mutating state operations (`POST`).
  - Mutating idempotency cache ensuring duplicate requests return identical results without repeated side-effects.
  - RFC 6455 WebSocket protocol upgrade handler transmitting real-time pipeline events, with automatic Server-Sent Events (SSE) fallback at `/api/v1/events`.
  - Strict Content-Security-Policy (`default-src 'self'`), `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY`.
- CLI Command:
  - `migration-agent ui [PATH]` and alias `agent ui [PATH]` supporting `--port` (`-p`), `--host`, `--open / --no-open`, and `--token`.
  - Validates target directory, launches server in background thread, opens browser automatically, and cleanly shuts down on Ctrl+C.
- Distribution Packaging Pipeline:
  - Release manifest generator and validator (`src/migration_agent/packaging/release_manifest.py`) computing canonical SHA-256 asset checksums, file sizes, and platform metadata.
  - Binary packaging specification and prompt cloaking pipeline (`src/migration_agent/packaging/build_binary.py`) providing PyInstaller standalone binary configuration with hidden imports, bundled UI data, and XOR/base64 prompt cloaking.
- Adversarial Security Matrix Tests:
  - Non-loopback binding rejection, Origin spoofing defense, missing/invalid CSRF rejection, session token authentication, mutating idempotency on terminal states, and release manifest integrity verification.

Completed on 2026-09-26 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
265 passed, 2 skipped in 66.31s

uv run ruff check .
All checks passed!

uv run ruff format --check .
140 files already formatted.

uv run mypy src
Success: no issues found in 63 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

A live UI smoke test confirmed:
1. `migration-agent ui tests/fixtures/fullstack-ecommerce-mini --port 8080 --no-open` starts the server and outputs tokenized launch URL.
2. Web UI loads runs, inspects plan steps, displays side-by-side diffs, generates Mermaid dependency graph, and verifies doctor checks via loopback REST API.
3. Live WebSocket broadcast pushes real-time log events to connected browser sessions.
4. Non-loopback origin requests are rejected with 403 Forbidden, and mutating state changes require valid CSRF and session tokens.



