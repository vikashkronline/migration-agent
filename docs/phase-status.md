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


## Phase 11 — Complete

Scope: Production Hardening and Real-World Migration Target (AngularJS 1.x to Modern Angular 17+ Standalone):
- Production Hardening:
  - Mode A Cryptographic Trust Store (`~/.agent-platform/trust/<project-id>.json`) adhering to ADR-2:
    - `AuthorityKey`, `RepositoryBinding`, `TrustRecord`, and `SignatureVerificationResult` domain models.
    - `LocalTrustStoreAdapter` managing authority public keys, repository bindings, and trust records out-of-band in developer user-data directory.
    - `CryptoSignatureVerifierAdapter` supporting Ed25519 and HMAC-SHA256 signature verification over RFC 8785 canonical metadata digests.
    - CLI approval integration (`migration-agent plan approve`) supporting `--signature`, `--key-id`, and `--trust-dir` with fallback to Mode B/C.
  - Containerized Command Execution Sandbox:
    - `ContainerizedCommandRunner` wrapping command execution in container engines (Docker/Podman) with strict command allowlists, read-only root volume mounts, dropped Linux capabilities, metacharacter defense, and graceful local runner fallback.
- Real-World Migration Target:
  - Real-world enterprise multi-file AngularJS dashboard fixture (`tests/fixtures/angularjs-realworld-dashboard`) containing directives (`user-profile`), components (`activity-feed`), services (`user-data`), templates, and CSS.
  - AST / regex transformation pipeline:
    - `AngularJsServiceExtractor` and `AngularStandaloneServiceRenderer` mapping `$http` calls to `HttpClient`, `Observable`, signals, and generating Jasmine unit test specs with `HttpTestingController`.
    - `AngularJsDirectiveExtractor` and `AngularStandaloneComponentRenderer` extracting components, directives, isolate scopes, bindings, and translating legacy templates to Modern Angular 17+ Standalone.
  - Strict Angular standards enforcement:
    - `standalone: true`, `ChangeDetectionStrategy.OnPush`, `@if` / `@for (...; track ...)` modern control flow syntax.
    - Angular Signals (`signal()`, `computed()`) and `inject(HttpClient)` dependency injection.
    - Modern Bootstrap 5 utility classes (`ms-auto`, `me-auto`, `d-none d-sm-block`, `col-*`) replacing Bootstrap 3/4 legacy classes (`pull-right`, `pull-left`, `hidden-xs`, `col-xs-*`).
- Offline Benchmark Evaluation:
  - Benchmark definition `bm-angularjs-realworld-dashboard` verifying 100% precision, recall, and F1 score against real-world AngularJS codebases offline.

Completed on 2026-09-26 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
279 passed, 2 skipped in 24.49s

uv run ruff check .
All checks passed!

uv run ruff format --check .
147 files already formatted.

uv run mypy src
Success: no issues found in 67 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.

uv run migration-agent eval tests/fixtures/angularjs-realworld-dashboard
Exit code 0; status: PASSED, precision: 1.00, recall: 1.00, f1_score: 1.00 in 15 ms.
```

## Phase 12 — Complete

Scope: Project Adoption, Curated Knowledge Lifecycle & Contextual Q&A:
- Git-Native Project Adoption & Initialization:
  - Scenario A (`migration-agent init`): Initializes greenfield target repositories with a complete `.agent/` directory structure (`manifest.json`, `policy.json`, `config.json`, `access/roles.json`, and knowledge subdirectories).
  - Scenario B (`migration-agent adopt`): Adopts existing repositories via read-only inspection, generating deterministic technology stack inventories, Architecture Overview documentation (`architecture.md`), and cross-domain Mermaid dependency graphs (`cross-domain-graph.md`). Enforces Invariant 25 (requires clean git working tree unless `--allow-dirty` is explicitly provided).
- Curated Knowledge Lifecycle (ADR-3, ADR-7, Invariant 16):
  - Epistemic status tracking (`EpistemicStatus`: `OBSERVED`, `INFERRED`, `HUMAN_CONFIRMED`).
  - Domain models: `ChallengeRecord`, `CandidateSolution`, `CuratedLearning`, `ArchitecturalDecisionRecord`.
  - `KnowledgePort` and `GitKnowledgeAdapter`: Human-readable Markdown frontmatter storage in `.agent/challenges/`, `.agent/solutions/`, `.agent/learnings/`, and `.agent/decisions/`.
  - `KnowledgeService`: Manages challenge recording, solution proposal, decision recording, and promotes candidate solutions to curated learnings strictly requiring human approval (`approved_by`, Invariant 16).
  - CLI subcommands: `migration-agent challenge`, `solution`, `learning`, `decision`.
- Contextual Technical Q&A Engine:
  - `ContextEnvelope`, `ContextualQARequest`, and `ContextualAnswer` domain models.
  - `ContextualQAService`: Gathers project context (manifest, policy digest, ADRs, curated learnings, eligible files, evidence references) and executes bounded LLM inquiries. Verifies citations against target repository files to detect and reject hallucinated file paths.
  - Runtime adapters: Deterministic `FakeAgentRuntime`, `OpenAIAgentsRuntime`, and `GeminiAgentRuntime` all implement `ask()` protocol.
  - Control API integration: `POST /api/v1/contextual-qa` and `POST /api/v1/ask` with loopback security, CSRF protection, and session authentication.
  - CLI command: `migration-agent ask <query> [--entity <path>] [--run-id <id>]`.

Completed on 2026-09-27 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
291 passed, 2 skipped in 23.13s

uv run ruff check .
All checks passed!

uv run ruff format --check .
158 files already formatted.

uv run mypy src
Success: no issues found in 74 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

## Section 15 Hardening — Adversarial Chaos & Security Test Matrix — Complete

Scope: Automated comprehensive verification of the 6 adversarial failure mode categories defined in Master Plan Section 15:
1. **Identity & Authorization Verification**:
   - RFC 8785 policy tampering and structural mutation detection.
   - Unknown authority key rejection on bootstrap and evaluation (Mode C fallback).
   - Repository binding defense (detecting and rejecting root commit SHA and remote origin spoofing).
   - Cryptographic signature integrity, empty signatures, invalid algorithm prefixes, and bit corruption detection.
   - Immediate authority key revocation enforcement.
   - Assurance boundary enforcement (Mode B/C inability to satisfy Mode A, step tampering post-approval invalidation).
2. **ChangeSet & Drift Invalidation**:
   - Tampered ChangeSet digest voiding apply token and triggering verified rollback.
   - Working-tree dirty drift detection aborting apply with `BASE_CHANGED`.
   - Target revision and plan drift invalidating approval.
   - Repair security context isolation (automated repairs generating fresh ChangeSets requiring re-approval).
3. **Apply Safety, Staging & Crash Recovery**:
   - ChangeSet directory traversal and path escape rejection during preflight.
   - Controlled simulated apply failure triggering clean, verified byte-level rollback.
   - Unrecoverable apply and rollback failure transitioning to `RECOVERY_REQUIRED` (Invariant 28) and recording durable recovery checkpoints.
4. **Event Store & Tamper Evidence**:
   - Strict monotonic timestamp and sequence ordering validation.
   - Audit trail tampering detection (out-of-order and retroactive timestamp modifications).
   - Split-brain rejection: SQLite checkpoint database as canonical authority over external JSONL exports.
   - Crash recovery resumption from persisted SQLite run records and checkpoint state.
5. **Native Controlled Execution & Sandboxing**:
   - Working directory confinement blocking path escape outside staging root.
   - Environment sanitization stripping developer credentials and tokens.
   - Command allowlisting blocking unapproved shell utilities.
   - Argument metacharacter inspection preventing shell injection attacks across both native and containerized runners.
   - Resource and timeout bounds terminating runaway processes cleanly.
6. **Control API & Local GUI Security**:
   - Origin spoofing defense (blocking unauthorized DNS rebinds and external origins with 403 `FORBIDDEN_ORIGIN`).
   - CSRF token enforcement blocking cross-site mutating requests with 403 `CSRF_REJECTED`.
   - Session authentication token validation rejecting forged or brute-forced tokens with 401 `UNAUTHORIZED`.
   - Strict 404 response for nonexistent routes and invalid request paths.

Completed on 2026-09-30 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
318 passed, 2 skipped in 48.49s

uv run ruff check .
All checks passed!

uv run ruff format --check .
165 files already formatted.

uv run mypy src
Success: no issues found in 74 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

## Hardening Milestone — Canonical CLI Binary Alias & Distribution Hardening — Complete

Scope: Canonical `agent` CLI identity, binary packaging pipeline, and cryptographically bound release manifests:
- Canonical CLI Binary Alias (`agent` + `migration-agent` backward compatibility):
  - Configured `agent` as the canonical executable entry point with `migration-agent` alias in `pyproject.toml` and CLI group registration.
  - Symmetrical multi-binary alias creation helper `create_binary_aliases()` supporting hardlinks, symlinks, and copies on Windows/POSIX.
  - Executable magic header inspection and integrity validation (`verify_binary_integrity()`) supporting PE (`MZ`), ELF (`\x7fELF`), and Mach-O formats.
- Standalone Binary Build Pipeline (`packaging/build_binary.py`):
  - Strongly typed `BinaryPackagingSpec` declaring entry points, canonical and alias names, comprehensive hidden imports covering all adapters/domains, data files, LTO, and stripping.
  - Deterministic PyInstaller `.spec` generator (`generate_pyinstaller_spec()`) and disk writer (`write_pyinstaller_spec_file()`).
  - Tier-1 platform heuristic and prompt cloaking / decloaking helpers (`cloak_prompt_string()`, `decloak_prompt_string()`).
- Cryptographically Bound Release Manifest (`packaging/release_manifest.py`):
  - Schema-versioned `ReleaseManifest` and `ReleaseAsset` models with deterministic asset classification (wheels, executables, source archives, signatures).
  - RFC 8785 canonical digest computation over release metadata (`compute_manifest_digest()`).
  - Cryptographic signing and verification integration via `CryptoSignatureVerifierAdapter` supporting Ed25519 and HMAC-SHA256 authority keys.
  - Manifest persistence and integrity verification (`save_release_manifest()`, `load_release_manifest()`, `verify_release_manifest()`).
- CLI Packaging Subcommands (`agent package` / `migration-agent package`):
  - `agent package spec`: generates or outputs PyInstaller build specification JSON.
  - `agent package manifest`: scans distribution artifacts, computes SHA-256 digests, and generates signed release manifests.
  - `agent package verify`: verifies published assets against `release-manifest.json`.
  - `agent package cloak` / `agent package decloak`: masks/unmasks prompt strings.

Completed on 2026-10-02 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
322 passed, 2 skipped in 32.94s

uv run ruff check .
All checks passed!

uv run ruff format --check .
165 files already formatted.

uv run mypy src
Success: no issues found in 74 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

## Phase 13 — Complete

Scope: Semantic Transformation Engine & Template Fidelity (Second Wave Hardening):
- Intermediate Component Typing & Capability Expansion (`ports/transformation.py`):
  - Expanded `IntermediateComponent` with typed properties: `injected_services: tuple[str, ...]`, `outputs: tuple[str, ...]`, `input_types: dict[str, str]`, `state_types: dict[str, str]`.
- Rich Semantic Extraction (`adapters/transforms.py`):
  - `AngularJsDirectiveExtractor.extract`: parses controller injection arguments, filters framework-internal dependencies (`$scope`, `$element`, `$attrs`), and identifies application service dependencies.
  - Extracts isolate scope bindings: typed inputs (`@`, `<`, `=`), outputs (`&`), and detects template expressions (`{{var}}`, `{{$ctrl.var}}`, `{{vm.var}}`).
  - Detects state property literal types (`boolean`, `number`, `any[]`) for typed signal initialization.
- Modern Angular 17+ Standalone Rendering Fidelity (`adapters/transforms.py`):
  - `render_component_ts`: renders typed inputs (`readonly name = input<string>('');`), typed state signals (`readonly isExpanded = signal<boolean>(false);`), outputs (`readonly update = output<any>();`), and modern Angular DI (`private readonly svc = inject(Svc);`).
  - `render_template_html`: dispatches to `migrate_template` for AngularJS components with template sources, preserving real DOM structures while modernizing directives.
  - `migrate_template`: converts Bootstrap 3/4 classes to Bootstrap 5 (`ms-auto`, `col-*`), converts events to `(click)`/`(ngSubmit)`, converts `ng-if` to modern `@if (...) { ... }` blocks, converts `ng-repeat` to `@for (...) { ... }` with tracking keys, and resolves signal function invocations (`{{ prop() }}`) while protecting loop variable references.
- Step-Bounded Transformation Scoping (`application/transformation.py`):
  - Enhanced `TransformationService.preview()` to support step-bounded filtering when `step_id` is provided. Matches component and service bundles against `target_step.expected_files`, names, and source files, producing clean, isolated ChangeSets for incremental step execution.
- Test Suite & Verification:
  - Comprehensive unit and contract tests verifying template preservation, signal resolution, typed DI, and step-bounded scoping.

Completed on 2026-10-02 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
324 passed, 2 skipped in 375.33s (0:06:15)

uv run ruff check .
All checks passed!

uv run ruff format --check .
165 files already formatted.

uv run mypy src
Success: no issues found in 74 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

## Phase 14 — Complete

Scope: Actionable Diagnostic-Driven Self-Repair Engine (Second Wave Hardening):
- Structured Diagnostic Parser (`application/diagnostics.py`):
  - Parses raw compiler (`tsc`), linter (ESLint), and test runner (Jasmine/Karma) stderr/stdout into typed `StructuredDiagnostic` instances.
  - Categorizes errors into `DiagnosticCategory` (`MISSING_IMPORT`, `SIGNAL_CALL_MISSING`, `SPEC_MOCK_MISSING`, `SYNTAX_ERROR`, `UNKNOWN`).
  - Extracts affected file path, line numbers, error codes (TS2304, TS2551, TS1005, TS2552, NullInjectorError), missing symbols, and suggestions.
- Surgical Deterministic Repair Strategies (`application/repair_strategies.py`):
  - `AutoImportRepairStrategy`: Automatically detects missing imports and synthesizes correct import statements. Maps well-known symbols (`Component`, `signal`, `input`, `output`, `inject`, `HttpClient`, `Observable`, etc.) to standard libraries (`@angular/core`, `@angular/common/http`, `rxjs`), merging into existing import declarations when present. For application services, searches across changeset diffs and workspace files for exported classes and generates relative POSIX imports (`./...` or `../...`).
  - `SignalCallRepairStrategy`: Detects uninvoked signal access (TS2551 / TS2339) in `.ts` class methods and `.html` templates and converts property access to signal calls (`this.prop` -> `this.prop()`, `{{ prop }}` -> `{{ prop() }}`).
  - `SpecTestBedRepairStrategy`: Catches `NullInjectorError: No provider for _HttpClient` in generated Jasmine test specs and inserts `provideHttpClient()` and `provideHttpClientTesting()` into `TestBed.configureTestingModule({ providers: [...] })`.
  - `SyntaxLintRepairStrategy`: Surgical insertion of missing semicolons and trimming of whitespace.
  - `DeterministicRepairEngine`: Orchestrates strategies in precedence order, filtering candidate changesets strictly against `allowed_scope`.
- Bounded Self-Repair Loop Integration (`application/validation.py`):
  - Integrated `DeterministicRepairEngine` directly into `BoundedRepairService.run_repair_loop`.
  - Deterministic surgical repair takes precedence over specialist diagnostician or default fallback, avoiding LLM calls for deterministic compilation/test failures while preserving Invariant 26 (fresh ChangeSet IDs, RFC 8785 digests, allowed scope boundary).
- Test Suite & Quality Gates:
  - Unit tests for all diagnostic patterns and deterministic repair strategies (`test_diagnostic_parser.py`, `test_deterministic_repair_strategies.py`).
  - All 6 quality gates passed.

Completed on 2026-10-02 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
337 passed, 2 skipped in 56.61s

uv run ruff check .
All checks passed!

uv run ruff format --check .
169 files already formatted.

uv run mypy src
Success: no issues found in 76 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

## Phase 15 — Complete

Scope: Streamlined Migration Pipeline & Semantic Evaluation (Second Wave Hardening):
- Unified Migration Pipeline Orchestration (`application/orchestration.py`):
  - Implemented `MigrationPipelineResult` and `MigrationPipelineService` coordinating preflight repository checks, Git clean working tree verification (Invariant 25), `.agent/` governance scaffolding, deterministic plan generation, interactive/automated Mode B plan approval, staging workspace materialization, validation gates with bounded self-repair, ADR-8 4-step controlled apply protocol with verified postconditions and backup snapshots, and dual-tier audit report compilation.
- CLI Integration (`agent migrate` / `migration-agent migrate` in `cli.py`):
  - Unified command: `agent migrate <path> [--step <id>] [--auto-approve] [--skip-validation] [--dry-run] [--allow-dirty] [--actor <name>] [--max-repairs <n>]`.
  - Supports `--dry-run` to preview ChangeSets and diffs safely without touching working trees.
  - Interactive terminal confirmation prompt for manual operator review or `--auto-approve` for non-interactive / automated CI/CD execution.
- Semantic Evaluation Benchmark (`application/evaluation.py`, `domain/evaluations.py`, `cli.py`):
  - Extended `EvaluationMetric` and `EvaluationBenchmark` with semantic metrics: `compilation_pass_rate`, `spec_pass_rate`, `control_flow_fidelity`.
  - Implemented `_evaluate_compilation` checking syntax correctness, balanced braces/parentheses, and valid TypeScript declarations across generated `.ts` files.
  - Implemented `_evaluate_specs` measuring Jasmine test spec completeness (`describe`, `it`, `expect`, `TestBed`).
  - Implemented `_evaluate_control_flow` measuring ratio of native Angular 17+ control flow blocks (`@if`, `@for`, `@switch`) versus legacy AngularJS directives (`ng-*`, `*ngIf`).
  - Added `--semantic` flag to `agent eval`.
- Test Suite & Quality Gates:
  - Unit tests for migration pipeline: `tests/unit/test_migration_pipeline.py`.
  - Unit tests for semantic evaluation: `tests/unit/test_semantic_evaluation.py`.
  - All 6 quality gates passed.

Completed on 2026-10-02 using `uv` and an isolated CPython 3.12.14 environment. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
345 passed, 2 skipped in 59.67s

uv run ruff check .
All checks passed!

uv run ruff format --check .
171 files already formatted.

uv run mypy src
Success: no issues found in 76 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```
