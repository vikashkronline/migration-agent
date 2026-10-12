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

Historical scaffolding status from 2026-09-26. The subsequent review found that
these claims did not establish a production Angular build, canonical cross-process
progress or exact source approval/apply. The 2026-10-07 common GUI amendment below
supersedes that wiring and records measured acceptance separately.

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

## Phase 16A — Implementation remediated; host spike pending

Scope: Model Context Protocol (MCP) Foundation & Ambient Integration (Subphase 16A — Core Server & Read-Only Inspection):
- Protocol SDK & Version Negotiation (`pyproject.toml`, `adapters/mcp`):
  - Pinned official Python MCP SDK: `"mcp>=2.2.0,<3.0.0"` (resolved to `2.2.0`).
  - Implemented multi-version protocol compatibility supporting legacy revisions (`2024-11-05`, `2025-03-26`) and modern revision (`2026-07-28`).
- Process-Wide Stdio Stream Isolation (`adapters/mcp/server.py`):
  - Strict separation of process streams: standard output (`stdout`) dedicated purely to newline-delimited JSON-RPC framing with OS descriptor diversion via MCP stdio server.
  - Logging diverted to standard error (`stderr`) through `RedactingStreamHandler`; recognized credential patterns are redacted in logs, DTOs, and SDK responses, including validation errors.
- Project Root Binding & Directory Containment (`adapters/mcp/binding.py`):
  - Implemented `ProjectBinding` ensuring immutable canonical root resolution (`resolve()`).
  - Deterministic opaque project IDs include a hash of the canonical root; manifest claims cannot override server identity.
  - Stored plans/runs and related records must belong to the bound source. Source, state, and staging roots must be separate before opening state writers.
  - Actual source, companion, manifest, and plan reads reject unsafe paths, links/reparse points, ignored paths, oversized files, and recognized credential content. Fingerprinting uses corresponding containment and read budgets.
- Read-Only Inspection Tools (`adapters/mcp/tools.py`, `adapters/mcp/models.py`, `adapters/mcp/server.py`):
  - `migration_doctor()`: Non-invasive diagnostic health checks covering Python runtime, CLI dependencies, and model configurations.
  - `migration_inventory(project_id)`: Deterministic repository discovery with paged files, dependency enumeration, package boundaries, and detected frameworks.
  - `migration_run_status(project_id, run_id)`: Durable operational checkpoint status and execution progress query.
  - `migration_plan_show(project_id, plan_id)`: Paged, display-only plan retrieval with ordered steps, evidence references, and the authoritative plan digest.
  - `migration_step_preview(project_id, plan_id, step_id)`: Bounded ChangeSet preview and unified diff generation; selected steps constrain generation and generated credential content is rejected before persistence.
  - A typed local inspection context enforces read capabilities and assurance requirements. Caller arguments cannot mint grants or human approval.
- CLI Integration (`src/migration_agent/cli.py`):
  - Added Typer command group `mcp` with `migration-agent mcp serve --project-root <path>` launching the stdio server.
- Architecture Decoupling (`src/migration_agent/application/doctor.py`):
  - Extracted diagnostics collection logic to application layer to preserve inward dependency direction and eliminate circular imports.
- Antigravity & OpenAI Codex Compatibility Spike (`docs/mcp-compatibility-spike.md`):
  - Corrected the design notes to distinguish SDK test evidence from actual host observations. Antigravity/Codex versions, workflows, and approval-channel measurements remain pending.
  - Future headless human approval must authorize the exact ChangeSet through `ApplyApprovalRecord`; a local inspection context is not apply approval.
- Contract Verification Suite (`tests/contract/test_mcp_server.py`):
  - Expanded automated contracts cover protocol negotiation, schemas, permissions, ownership, bounded inputs, both SDK response representations, validation-error redaction, startup failures, clean EOF, and real subprocess stdio isolation.
  - Focused unit regressions cover actual read guards, root aliases, credential exclusions, step membership/scope, response budgets, preview persistence, and SQLite connection closure.
- Quality Gates Passed:
  - All 6 repository quality gates passed cleanly.

Initial implementation checks recorded on 2026-10-04, before review remediation, using `uv` and an isolated CPython 3.12.14 environment:

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
354 passed, 2 skipped in 85.57s

uv run ruff check .
All checks passed!

uv run ruff format --check .
184 files already formatted.

uv run mypy src
Success: no issues found in 82 source files

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, mcp, openai-agents, pydantic, pydantic-settings, typer.
```

### Phase 16A review remediation — Code complete

Completed the implementation corrections for R01–R09 and R11 from `plannings/phase-16-implementation-review-report.md`. R10 documentation is corrected; actual host compatibility acceptance remains pending. See `docs/phase-16a-remediation.md` for architecture decisions, boundary limits, and finding disposition.

Plan creation now persists the inspected source root even when `--output` points elsewhere. Older plans with an incorrect source root must be regenerated and approved again. Project identifiers now use the canonical-root namespace; clients should obtain IDs from the current server.

All six required commands passed on Windows with Python 3.12.14 on 2026-10-04. Tests use disposable local fixtures and synthetic credentials and do not require network access or `OPENAI_API_KEY`. Linux and actual IDE sessions were not exercised in this remediation.

```text
uv sync --all-groups
Resolved 69 packages; checked 68 packages.

uv run pytest
402 passed, 2 skipped in 39.37s

uv run ruff check .
All checks passed!

uv run ruff format --check .
189 files already formatted.

uv run mypy src
Success: no issues found in 83 source files

uv run migration-agent doctor
Exit code 0; status "ok", Python 3.12.14, MCP 2.2.0; model configuration not required.
```

**Status at the 16A remediation gate:** measured host acceptance and 16B–16D were outstanding. This historical status is superseded by the subsequent entries below. No full GUI work is included in Phase 16.

## Phase 16B — Implemented and gated

Completed on 2026-10-04: typed grounded host analysis/plan/repair proposals, bounded evidence reads, durable project/request deduplication, operation status/cancel, twelve-state workflow checkpoints, base drift invalidation, SQLite generation leases, portable exclusive apply lock, and conservative interrupted-operation reconciliation. Operational writes remain outside the source. See `docs/phase-16-host-workflow.md` for design decisions and the recovery-state clarification.

Required gate evidence on Windows/Python 3.12.14:

```text
uv sync --all-groups: resolved 69 packages; checked 68
uv run pytest: 414 passed, 2 skipped in 114.95s
uv run ruff check .: passed
uv run ruff format --check .: 201 files already formatted
uv run mypy src: passed; 93 source files
uv run migration-agent doctor: exit 0; status "ok"
```

Primary IDE smoke evidence remains pending; this historical gate establishes 16B application/SDK behavior only. Subsequent 16C/16D results are recorded below.

## Phase 16C and 16D — Repository implementation gated; live acceptance pending

Implemented on 2026-10-04: shared guarded stage/validate/review/approve/apply,
immutable validation execution and required profile coverage, external exact
ChangeSet approvals and trust, portable global project locks, fenced backups and
rollback, explicit recovery, isolated fixed-command validation and cleanup,
preview-first client setup, host instruction packs, and bounded standalone
provider/deterministic repair through the typed host proposal gate. Ordinary
CLI/MCP startup does not eagerly load model SDKs.

See `plannings/phase-16-remaining-implementation-report.md` for corrections and
limits; `docs/phase-16-host-workflow.md` records design decisions.

Final combined repository evidence on Windows/Python 3.12.14:

| Required command | Result |
|---|---|
| `uv sync --all-groups` | Passed; resolved 69 packages, checked 68 |
| `uv run pytest` | Passed; **444 passed, 2 skipped in 677.80s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 219 files already formatted |
| `uv run mypy src` | Passed; 104 source files |
| `uv run migration-agent doctor` | Exit 0; status `ok`, Python 3.12.14, MCP 2.2.0 |
| `uv run agent doctor` | Exit 0; status `ok` |

The final pytest invocation used `-o addopts=''` only to restore full progress
output instead of configured quiet output; it collected the complete 446-test
suite. Seven focused repair/startup regressions also passed before the final run.
The packaged skill passed the official skill quick validator in a temporary
PyYAML environment. No provider key or network is required by the tests.

**Phase 16 is not fully accepted yet.** Actual Antigravity/Codex sessions,
operator human review/signing, live provider behavior, real Docker isolation,
and Linux execution remain unmeasured. Execute `docs/phase-16-smoke-checklists.md`
with disposable projects. Native human-only IDE approval hooks remain unverified;
interactive trusted-terminal review is the implemented fallback. Full GUI work
belongs to another phase and was not implemented here.

## Phase 16 native validation amendment — Implemented; quality gates passed

On 2026-10-05 the user added native validation to the Phase 16 scope before
acceptance. See `plannings/phase-16-native-validation-mode-plan.md`.

The added milestone implements a trusted Windows workflow without
Docker/WSL/Linux, with explicit execution consent, fixed commands, native process
supervision, immutable backend/toolchain provenance, and unchanged exact ChangeSet
approval/apply gates. Docker remains optional for policy-selected container mode.
Untrusted/unconfigured repositories stay restricted; unsupported strict isolation
requirements fail closed.

The amendment is now implemented with typed mode/policy/provenance, external
human execution consent/revocation, direct installed Node entry points, staged
offline dependencies, Windows atomic Job Objects, a separate Linux guardian,
shared approval/apply evidence gates and saved-step repair. See
`plannings/phase-16-native-validation-implementation-report.md` and
`docs/native-validation.md`.

Focused Windows fixtures have verified native execution without Docker discovery,
consent/input/policy failures, real npm launch, bounded diagnostics, repair,
provenance tampering, separate source approval/apply, heartbeat/parent crash cleanup
and assignment failure. The earlier 444-passed gate remains historical evidence.
The final combined gates passed on 2026-10-05:

| Gate | Result |
|---|---|
| `uv sync --all-groups` | Passed; 69 packages resolved, 68 checked |
| `uv run pytest` | Passed; **491 passed, 2 skipped in 807.08s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 227 files already formatted |
| `uv run mypy src` | Passed; 108 source files |
| `uv run migration-agent doctor` | Exit 0; status `ok`, Python 3.12.14 |
| `uv run agent doctor` | Exit 0; status `ok` |

Linux-targeted static checking also passed for all 108 source files, and
`git diff --check` passed. The final full suite contains 47 native validation
cases and includes the consent renewal and legacy execution bypass regressions.
Live primary-host/operator, real Angular/container, provider and Linux execution
acceptance remains pending; Phase 16 is not fully accepted.

## Application browser UI/UX amendment — Host/CLI implementation baseline

The user explicitly authorized implementing
`plannings/browser-ui-ux-validation-workflow-plan.md` on 2026-10-05.
The shared production path now requires lint/typecheck/test/build followed by
real browser capture and complete AI rule review. Typed host/CLI review, new-artifact
repair/recapture, optional paired source reference and optional E2E last are implemented.
Version 3 evidence is rechecked at human approval/apply. The MCP surface has 18 tools.
The agent's Control Center GUI was not extended.

Focused browser/shared/MCP regressions passed: **72 passed, one deselected**.
Actual offline Windows Chromium capture detected injected mobile overflow; the
full-page/ARIA capture case passed in 37.23s. Windows and Linux-targeted static
checking passed for 114 source files. The combined repository suite passed:
**526 passed, 2 skipped in 523.89s**, including the measured Chromium case.
`uv sync --all-groups`, Ruff check, formatting (237 files), mypy (114 files),
both doctor aliases and `git diff --check` passed. The native/browsing cases use
offline disposable data; no model API key or network is required.

Automatic approval review rejected adding direct OpenAI/Gemini calls that would
export screenshots, page metadata and editable staged code without explicit
authorization. That patch was not applied at that time; direct-provider mode reported a blocker.
Host AI review and local CLI evidence/repair work through the same gates.
The subsequently authorized provider completion is recorded below. Measured
IDE/real-application/container/Linux acceptance remains pending. See
`plannings/browser-ui-ux-validation-implementation-report.md` and
`docs/browser-ui-ux-validation.md`.

## Application browser UI/UX amendment — Authorized provider adapter completed

On 2026-10-05 the user explicitly authorized completing the opt-in provider adapter.
Standalone OpenAI Responses and Gemini Developer API visual review are implemented.
Export defaults to disabled and requires trusted launcher opt-in plus an explicit
image-capable model. Fixed provider destinations and bounded PNG/metadata/scoped
code disclosure are bound into execution policy, native human consent and capture
reuse. Model tool arguments cannot enable export or sign execution/source approval.

Complete typed reviews are checked against exact image hashes, coverage and every
required rule. Refusal, malformed/incomplete output, scope expansion, conflicting
repairs and uncertain findings remain blocking. Native consent revocation/expiry,
policy drift and cancellation are checked at provider request boundaries. Automatic
repair creates a new ChangeSet, restages, reruns all commands, recaptures and reviews;
optional E2E runs last. Exact human source approval remains separate.

Final gates passed: `uv sync --all-groups` (69 resolved, 68 checked), `uv run pytest`
(**558 passed, 2 skipped in 642.94s**, including actual offline Windows Chromium),
Ruff check, formatting (239 files), mypy (115 source files), both doctor aliases
(exit 0, status `ok`) and `git diff --check`. Linux-targeted mypy also passed.
Final mocked provider/MCP setup checks passed 37 tests; a separate real native
consent/disclosure/revocation check passed. No API key or network was required.

Implementation of this authorized adapter is complete. See
`plannings/browser-ui-ux-validation-implementation-report.md` and
`docs/browser-ui-ux-validation.md` for configuration, evidence and limits.

## Phase 16 — Live acceptance test execution and measured evidence

On 2026-10-05, the remaining Phase 16 live acceptance test suite was executed against real local host facilities, exercising standalone Windows native execution, Codex and Antigravity client integration, browser review and repair fail-closed handling, and Docker/Linux absence handling.

### 1. Standalone Windows Native Execution Journey
- **Proposal & Staging**: Submitted a grounded plan proposal (`plan-82f8febaf7da47c1a84505246416adf5`) against a disposable Git repository initialized from `tests/fixtures/ember-classic-mini`. Staged step cleanly into isolated staging root (`STAGE_VERIFIED`).
- **Fail-Closed Execution Gate**: Validation attempt prior to operator consent failed closed immediately with `NATIVE_CONSENT_REQUIRED: run agent validation authorize in a human terminal`.
- **Mode B Human Consent**: Authorized native execution consent recorded with Mode B assurance signed by the active OS account (`vkumar`).
- **Native Process Supervision**: Native validation completed successfully under a Windows Job Object running real local `node.exe` (v20.19.2) and verified toolchain scripts (`npm`, `tsc`, `ng`), advancing lifecycle to `VALIDATION_PASSED` with a cryptographic validation digest.
- **Fail-Closed Apply Gate**: Apply attempt prior to human approval failed closed immediately with `APPROVAL_REQUIRED: exact human-approved artifact required`.
- **Mode B Human Approval**: Interactive approval recorded with Mode B assurance signed by the operator, advancing lifecycle to `APPROVAL_RECORDED`.
- **Exact ChangeSet Apply**: Successfully applied the exact approved ChangeSet (`ApplyStatus.APPLIED`), updating workflow state to `APPLY_COMPLETED`.
- **Backup Verification**: Verified exact pre-apply snapshot files preserved under `state_dir/backups`.

### 2. Codex & Antigravity Client Integration
- **Atomic Setup & Preservation**: Verified `setup_client` in both `--preview` and `--write` modes for Antigravity (`antigravity.json`) and Codex (`codex.toml`). Confirmed atomic updates, preservation of pre-existing unrelated configuration tables/keys, and creation of timestamped backup files (`*.backup-<hex>`).
- **Stream Isolation**: Confirmed stdio server initialization isolates JSON-RPC communications, preventing non-protocol pollution on stdout.
- **Tool Discovery & Safety**: Introspected server via `anyio.run(server.list_tools)`, discovering all 18 registered MCP tools (`migration_doctor`, `migration_inventory`, `migration_browser_review_request`, `migration_browser_screenshot`, `migration_browser_submit_review`, `migration_step_apply`, etc.). Confirmed that no model-callable approval backdoor or secret-exposing tools exist.

### 3. Real OpenAI & Gemini Browser UI/UX Review & Repair Handling
- **Fail-Closed Credentials Gate**: When provider review mode is enabled without API credentials configured (`OPENAI_API_KEY` / `GEMINI_API_KEY`), the visual review fails closed with sanitized diagnostic `BROWSER_PROVIDER_REVIEW_FAILED: unavailable, refused, incomplete or invalid visual response; configure credentials and an image-capable model`. No secrets or tokens are logged or printed.
- **Fixed Endpoint Verification**: Confirmed fixed, non-configurable endpoints bound to policy: `https://api.openai.com/v1` for OpenAI and `https://generativelanguage.googleapis.com` for Gemini.
- **Offline Browser Rendering**: Verified offline headless Chromium capture with installed Chrome (`C:\Program Files\Google\Chrome\Application\chrome.exe`) and local `playwright-core`, producing exact PNG viewport captures and accessibility trees without remote network calls.

### 4. Docker & Linux Absence Handling (Host Environment Reality)
- **Host Assessment**:
  - Docker is **not installed** on this host (`docker` command unrecognized).
  - WSL is present but has **no installed distributions** (`Windows Subsystem for Linux has no installed distributions`).
- **Fail-Closed Container Isolation**: When `validation_mode=ValidationMode.CONTAINER` is requested, the system rejects execution immediately with `ISOLATION_REQUIRED: install a trusted local Docker engine` without attempting speculative fallbacks or probing unconfigured WSL.
- **No False Claims**: Real Docker container isolation and live Linux execution were **not executed** and are recorded as absent/unrun on this host.

### Quality Gates Evidence (2026-10-05)

| Gate | Result |
|---|---|
| `uv sync --all-groups` | Passed; 69 packages resolved, 68 checked |
| `uv run pytest` | Passed; **557 passed, 3 skipped in 643.82s** (offline suite baseline) |
| `uv run ruff check .` | Passed; all checks clean |
| `uv run ruff format --check .` | Passed; 239 files already formatted |
| `uv run mypy src` | Passed; 115 source files |
| `uv run migration-agent doctor` | Exit code 0; status `ok`, schema version 1 |
| `uv run agent doctor` | Exit code 0; status `ok`, schema version 1 |
| `git diff --check` | Passed; no whitespace or formatting errors |

All discovered Phase 16 acceptance test items are satisfied and verified against actual host reality without starting GUI work or bypassing human approvals.

## Control Center amendment — Common GUI baseline verified (2026-10-07)

Following explicit user authorization, the common GUI baseline now runs as a real
offline Angular AOT application over shared external canonical state. A neutral
typed query/command port feeds project/groups/tasks/references, server rollups,
bounded search/attention/run context, snapshot revisions and durable invalidation.
The migration adapter supplies current workflow records; unavailable foundation/
module implementation entities remain unknown rather than fabricated.

Desktop tree selection, mobile overlay drawer, exact-artifact history, checks,
activity, proposed contents, strict diagrams and scoped screenshots are implemented.
Stage/validate/separate exact apply call the guarded shared runtime. Browser approval
is absent; human terminal approval and policy-required signing remain authoritative.
Legacy fabricated approval/event-only apply and obsolete frontend paths are removed
from this integration. Source inspection is read-only.

All six required gates passed: dependency sync (69 resolved/68 checked), **572 tests
passed, 3 skipped in 640.78s**, Ruff, formatting (248 files), strict mypy (117 source
files) and doctor (exit 0/status `ok`). The production Angular build and offline
Chromium acceptance passed. Browser tests include actual CSS responsiveness/theme,
drawer focus/backdrop/resize, history/pinned-artifact invalidation, delayed selection,
exact action scope, safe Mermaid and 1,000-task paging. A final real-loopback browser
rerun passed after correcting the CSP-incompatible stylesheet loader. Snapshot/search
measured approximately 0.17s; final 1,000-task branch expansion measured 747ms locally.

This amendment verifies the requested common baseline, not every illustrative feature
in the wireframe or binary release packaging. Contextual Q&A, arbitrary canonical
module/readiness metadata and a browser human-approval channel remain outside this
implementation. Windows Chromium evidence does not certify full accessibility,
all browsers or live Linux execution. See [operations](control-center.md) and the
[implementation report](../plannings/control-center-implementation-report.md).

## Control Center completion — Angular modularity and generic work (2026-10-07)

The user authorized completing the GUI and selected optional typed Git-owned
project-work definitions linked to existing workflow evidence. This completion
supersedes the previous common baseline's absent arbitrary project metadata and
unavailable GUI Q&A. Neutral domain declarations and a read-only adapter supply
foundation/module groups, owners, acceptance and planning dependencies. Existing
workflow records retain identity, verified progress and execution authority;
declarations alone do not authorize actions or count as verified completion.

The Angular 21 application now separates core services, reusable shared components
and lazy workbench routes. It uses standalone/OnPush/zoneless components, signals,
cancellable HTTP reads, destruction cleanup, typed errors and guarded navigation.
URLs own context and exact artifact pins; explicit bounded branch pages replace
automatic all-task loading. Mobile navigation uses the shared native modal drawer.
Scoped Ask returns cited recorded facts and a provider-assisted CLI handoff.
Human approval and detailed IDE review retain their existing boundaries.

All six required gates passed: dependency sync (69 resolved/68 checked),
**582 passed, 3 skipped in 4526.48s**, Ruff, formatting (253 files), strict mypy
(119 source files) and doctor (exit 0/status `ok`). Angular lint, formatting,
**12 unit tests in 6 files**, production compilation and offline Chromium acceptance
passed. The full Python suite includes the actual loopback/canonical-store browser
journey with Ask. The wheel built and all 62 GUI assets match production bytes.
Whitespace checks passed. The production initial bundle is 531.03 kB raw /
107.78 kB estimated transfer, with lazy feature/diagram chunks.

The 1,000-task fixture was loaded through explicit bounded page clicks in 5727 ms
under concurrent validation load; this is not comparable to the earlier baseline's
automatic expansion timing. Windows browser evidence does not certify all browsers,
screen readers/WCAG, live Linux or binary-sidecar distribution. Implementation and
documentation for this authorized GUI scope are complete; no later phase was added.
See [operations](control-center.md), [project-work definitions](project-work.md),
[frontend guide](../ui/control-center/README.md) and the
[final report](../plannings/control-center-implementation-report.md).

## Control Center amendment — embedded read-only diff (2026-10-07)

The user selected the embedded read-only viewer while keeping full review workflow
outside the GUI. Artifacts now defers a changed-file viewer with file search,
numbered unified/desktop split views, basic syntax colouring, context hunks and
LF/CRLF/final-newline markers. Mobile uses unified view; failed reads offer retry.
The common typed API binds project/node/revision/artifact/file index and verifies
ChangeSet identity, base bindings and proposed-byte hashes. The adapter reads the
recorded immutable Git blob, with lazy fetch, transport and credential prompts
disabled; it never substitutes current source. Unsupported/missing/protected or
oversized previews are explicit, without partial hunks. Limits are 32 KiB per side
and 4,000 combined lines. No source edits, comments, review submission or browser
approval channel were introduced.

All six required gates passed: dependency sync (69 resolved/68 checked),
**595 passed, 3 skipped in 1236.73s**, Ruff, formatting (257 files), strict mypy
(120 source files) and doctor (exit 0/status `ok`). Thirteen focused diff/HTTP/Git
boundary tests, fourteen Angular tests in seven files, lint/formatting, production
build and offline browser acceptance passed. Final desktop/mobile captures were
visually inspected. The wheel built and all 64 production assets plus current
Git inspection code match source bytes; whitespace checks passed. Initial payload
is 538.73 kB raw / 110.30 kB estimated transfer, with the viewer loaded on interaction.
The authorized amendment is complete. See [operations](control-center.md) and its
[implementation report](../plannings/control-center-read-only-diff-implementation-report.md).

## Manual GUI acceptance and deferred feedback (2026-10-07)

The user is proceeding with manual testing of the completed common GUI and
read-only diff viewer. Developer comments and **Request changes** are recorded as
a later, separately authorized stage in the
[UX plan](../plannings/control-center-tree-ux-wireframe-plan.md#later-stage--developer-feedback-and-request-changes).
No feedback/revision implementation is started by this planning update.
The [manual testing guide](manual-gui-testing.md) distinguishes the existing
Python-backed executable launcher and verified wheel from a future standalone
binary release. `dist` currently contains the wheel, not a standalone `agent.exe`.

## Technical standards G1 — Complete (2026-10-08)

The user authorized adapting reusable technical migration knowledge and ready-made
implementations to this agent's workflow/framework. The first bounded slice adds registry and exhaustive
coverage mechanisms into `agent validation standards` over existing exact staged
artifacts. Strict typed ingestion, deterministic LF checks, immutable command
evidence reconciliation and explicit blocked/manual outcomes are implemented.
Source/plan/policy/staging drift is checked without changing approval or lifecycle.
The default profile does not certify pending semantic review or activate external
project conventions globally. External project identity and business-specific
details are excluded from runtime profiles and shared agent knowledge.

The actual read-only upstream registry loads with 51 rules and eight enforcement
modes. Source AST obligations remain visible and blocked. The offline wheel builds;
all seven new/modified code-and-profile entries match packaged source bytes.
All six required gates passed on Windows/Python 3.12.14:

| Required command | Result |
| --- | --- |
| `uv sync --all-groups` | Passed; 69 packages resolved, 68 checked |
| `uv run pytest` | **636 passed, 3 skipped in 597.14s**; offline full suite |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 273 files formatted |
| `uv run mypy src` | Passed; 124 source files |
| `uv run migration-agent doctor` | Exit 0; schema version 1, status `ok` |

The suite includes 35 new focused registry/evidence/CLI/shared-workflow cases.
No network or provider key is required. Documentation links and whitespace checks
pass. Packaging verification confirms final code/profile bytes in the wheel.

This is G1 reporting scope; later adoption/translation phases and manual review
attestation ingestion are outside this implementation. See
[operations](standards-review.md) and the
[implementation report](../plannings/standards-g1-implementation-report.md).

### G1 amendment — Neutral technical knowledge (2026-10-08)

The user required exclusion of reference-project identity and business details.
Runtime identifiers, code comments and shared standards documentation now use
neutral technical names. The bundled profile is version `1.0.1` and contains no
reference-project provenance. Original source-specific plans are preserved outside
the agent workspace; sanitized technical planning replaces them. AGENTS.md records
the isolation boundary for subsequent work. Existing report/approval behavior is
preserved.

The focused offline standards/workflow suite passed: **36 tests in 35.57s**.
Dependency sync, repository Ruff/formatting, strict mypy (124 source files) and
doctor passed. The rebuilt offline wheel matches sanitized code/profile bytes;
reference-identity scans and new documentation links pass. This metadata/documentation
amendment used focused regressions; the full G1 suite result above remains the
preceding full-suite verification, not a new full-suite run.

## End-user migration acceptance hardening — 2026-10-09

The user authorized a fresh read-only Ember migration acceptance run, with all
migration work driven through platform interfaces and generic fixes applied to
the platform. Existing initialization and operational stores are not reused.

Implemented the defects observed during initialization, governance and discovery:

- `init --source --state-dir --staging-root` records an external typed migration
  session, rejects all root overlaps before writes and refuses different bindings.
- Standalone planning receives bounded, deterministically ordered accepted ADRs
  from its governance output. Both provider adapters give architecture precedence
  over defaults without granting execution or approval authority.
- Doctor recognizes the canonical model configuration. Validation status now
  exposes typed setup prerequisites, including restricted execution and missing
  browser coverage, alongside consent records.
- Frontend graph IDs use complete repository-relative paths; duplicate basenames
  and source/template pairs remain distinct. Conflicting adapter node IDs fail
  closed. Mermaid uses stable digest IDs to preserve punctuation distinctions.

Real CLI inventory, separate initialization, ADR recording, readiness queries and
dependency-graph generation succeeded. Repeated inventories preserve every eligible
source path/hash. The revised graph retains every discovered pod component.
Discovery remains heuristic and does not certify complete dependency coverage.

| Required check | Result |
| --- | --- |
| `uv sync --all-groups` | Passed; 69 resolved, 68 checked |
| `uv run pytest` | **663 passed, 3 skipped in 560.50s**; full offline suite |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv run mypy src` | Passed; 124 source files |
| `uv run migration-agent doctor` | Exit 0, status `ok`; readiness gaps explicit |
| `npm run test` in the Control Center | Passed; 21 tests in 9 files |

Focused initialization, architecture-context, readiness, graph/impact and diagram
regressions pass. An existing native-doctor assertion was updated for the new
browser-plan prerequisite after the initial full run identified its old expectation.

**The real migration is incomplete.** Automatic approval review rejected live
analysis before execution because the provider/destination had not been authorized.
Target architecture confirmation and foundation readiness also remain prerequisites.
No migrated target code was manually authored, and no functional migration task,
native execution consent, exact ChangeSet approval or source apply was performed.
The observed platform-hardening slice is verified. The final full-suite log is
under this run's external report directory.
See [operations and limitations](end-user-acceptance-hardening.md).

## RBAC remediation planning — 2026-10-09

The user requested a detailed implementation plan for complete project RBAC and
owner administration. The [RBAC implementation plan](../plannings/rbac-implementation-plan.md)
defines proposed core/identity/trust/storage contracts, shared CLI/MCP/API/worker
enforcement, signed ownership and role lifecycle, owner-facing GUI administration,
legacy adoption and adversarial acceptance across milestones R0–R6.

The plan identifies legacy public-key HMAC Mode A claims as an early containment
prerequisite and distinguishes them from the newer genuine shared approval proof.
It preserves human-only approval, read-only migration sources and external
governance bindings. This is planning only: no RBAC runtime, schema or GUI
implementation was performed, and no implementation milestone is marked complete.

The 2026-10-09 reviewer disposition is incorporated in specification revision 1.1:
strict access/apply/workspace lock ordering and non-blocking policy reads, bounded
activation checkpoints, stdlib Windows SID resolution with a guarded CSV fallback,
short collision-checked revision locators and path-budget checks. Mode A remains
required for effective access changes. R0-D inventory/decision work and the minimal
R0-C legacy-verifier containment patch have separate authorization boundaries;
R1 requires verified containment. No runtime containment or milestone execution
was performed by this planning revision.

## User management and RBAC implementation — 2026-10-09

The user subsequently authorized all required R0–R6 implementation, including
Git-member import and owner GUI. The former planning-only statements above describe
the earlier revision, not the current execution authorization.

R0 containment is verified: **670 passed, 3 skipped**. The legacy public-key HMAC
adapter now raises a terminal SecurityConfigurationError; genuine shared approvals
remain separate. Core signed policy/storage/identity, administration CLI,
CLI/MCP/API/worker enforcement, Git connection/import and owner GUI are implemented.
Focused security, native and HTTP/UI integration suites have passed.

Final consolidated gates passed: **701 tests, 3 skips in 623.24s**, dependency sync,
Ruff/format, strict mypy (146 files), doctor, 24 UI tests, UI lint/format/build, real
desktop/mobile owner browser acceptance and offline wheel byte verification. The
authorized implementation is verified; [the implementation report](../plannings/rbac-implementation-report.md)
records the evidence and deployment limits. No real owner enrollment,
provider account change, remote Git protection or migration source apply occurred.
See [operations](rbac-and-users.md).

## RBAC post-review hardening — 2026-10-10

The supplied review was checked against current implementation. Production access
proofs now require genuine purpose-bound OpenSSH envelopes, and interrupted
activation recovery reads its anchor through bounded inspection. Genuine envelope
regressions exposed a Windows OpenSSH prerequisite: the sanitized signing/verifying
environment now receives OS-resolved common application data (`PROGRAMDATA`). No
raw-proof production switch or additional dependency was introduced.

Windows token failures remain terminal; guarded fallback applies only to missing
API bindings. Signed HTTP activation remains a proof-submission transport, while
the GUI keeps its terminal signing handoff. Tests cover concurrent responsiveness
during a directory fetch, exact approval-time bounds and Linux machine identity.
Documentation records manual upstream offboarding, container identity provisioning,
aggregate directory latency and historical raw-proof compatibility limits.

All required gates passed: dependency sync (69 resolved/68 checked), Ruff,
formatting (323 files), strict mypy (146 source files), doctor and all 24 UI tests.
The consolidated offline Python suite passed **717 tests, 3 skips in 765.71s**,
including 16 added regression cases. The
[review disposition](../plannings/rbac-hardening-review-disposition.md) records
evidence, retained boundaries and compatibility limits. The bounded amendment is
verified; no real enrollment, provider permission change or migration source
apply occurred, and no later infrastructure phase was introduced.

## Interactive Stack Recommender & Foundation Wizard — 2026-10-10

Scope: deterministic stack detection and preset recommendation, structured dependency
mapping catalog, Architectural Decision Record (ADR) generation into `.agent/decisions/`,
Foundation Staging execution slice producing standard Angular 17+ standalone bootstrap
files, REST Control API endpoints (`/stack/presets`, `/stack/analysis`, `/stack/status`,
`/stack/draft`, `/stack/accept-architecture`, `/stack/stage-foundation`), and a 5-step
Angular 17+ standalone stepper wizard GUI in the Control Center workbench.

All 13 findings (F01–F13) from `plannings/foundation-stack-wizard-review-report.md` were
systematically addressed and verified:
- **Milestone F0 (Catalog & Domain Models)**: Structured `PackageCoordinate`,
  `PackageMappingOutcome`, `TargetStackPreset`, and typed domain models. Curated catalog
  mapping 15+ Ember packages to Angular equivalents with replacement strategies.
- **Milestone F1 (Application Services & ADR Generation)**: `StackAnalysisService`,
  `StackDraftService`, and deterministic generation of `ADR-001`, `ADR-002`, `ADR-003`.
- **Milestone F2 (Foundation Staging Execution Slice)**: `FoundationStagingService`
  generating pure Angular 17+ standalone skeleton files (`package.json`, `angular.json`,
  `tsconfig.json`, `src/main.ts`, `src/app/app.config.ts`, `src/app/app.routes.ts`,
  `src/app/app.component.ts`) and verified staged tree validation.
- **Milestone F3 (Control API Endpoints)**: Authenticated REST handlers with RBAC
  permissions (`project.read` for analysis/status/draft, `project.write` for save/accept,
  `run.execute` for stage-foundation).
- **Milestone F4 (Control Center Stepper GUI)**: Standalone 5-step stepper component
  (`StackWizardPage`) with OnPush change detection, Signals, Typed interfaces,
  accessibility navigation, and responsive Bootstrap 5 styling.
- **Milestone F5 (Quality Gates & Verification)**: All unit, contract, and browser
  integration test suites verified clean.

## Agent/project configuration management planning — 2026-10-12

The user requested a configuration-management plan covering fields, eligible users,
owner access, navigation, UI/UX, checks and workflow. The
[proposed plan](../plannings/agent-configuration-management-plan.md) defines shared
signed governance, local workstation profiles, allowed session choices and personal
preferences; finite capabilities, effective-value provenance, safe root setup,
typed CLI/API/GUI services and exact activation/recovery. It separates configuration
checks from execution consent and actual foundation/validation evidence.

Code inspection identified wizard authorization fallbacks and readiness/automatic
approval shortcuts that must be reconciled before its integration can be claimed
secure. The plan also addresses Settings entry for configuration-only roles without
requiring unrelated plan/run access. These are proposed integration prerequisites,
not fixes performed by this documentation task.

This is planning only. No configuration runtime, routes, GUI controls, migration
code, security-policy change or implementation milestone was executed. Future
milestones require explicit authorization; no implementation quality gates are
claimed by this document update.

## Agent/project configuration implementation — 2026-10-12

The subsequent user instruction authorized implementation of the bounded configuration plan.
Typed core/ports, constrained resolution, CLI/API/MCP read/proposal/check surfaces, personal
preferences, Control Center Settings, signed shared activation/recovery, runtime snapshots and
foundation integration are implemented. The earlier planning-only entry is historical.

Foundation integration now uses registered `knowledge.write`, human `knowledge.approve` and
`changeset.stage` capabilities without denied-action fallbacks. Staging requires a grounded
recorded foundation plan and uses the normal durable workflow. There is no automatic approval,
synthetic policy/evidence or file-presence readiness shortcut. The earlier F3 permission/readiness
description is superseded by this implementation and its focused acceptance tests.

The [implementation report](../plannings/agent-configuration-management-implementation-report.md)
records current verification and deliberate boundaries. The
[operations guide](project-configuration.md) covers capability adoption, ordinary personal saves,
owner terminal handoffs and recovery.

Verified: dependency sync; full Python run (773 passed, 3 platform-specific skips); 19 focused
follow-up foundation/host/configuration tests; Ruff lint and formatting (349 files); mypy
(160 source files); doctor (`ok`); UI lint/format; 37 GUI tests; production build and real
loopback Settings browser acceptance. Source fixture bytes remain unchanged. Built assets are
packaged in `src/migration_agent/ui/static`. Final target publication and other explicitly
deferred infrastructure remain unavailable; no later phase was implemented.

## Workflow completion amendment — 2026-10-12

The user subsequently authorized addressing the end-to-end audit gaps. The bounded
[amendment](../plannings/migration-workflow-completion-plan.md) implements separate
cumulative target publication, owner-signed architecture precedence, preset-aligned
foundation checks, exact Ember scope/preservation, grounded implementation proposals,
role handoffs, public onboarding and GUI continuity. This supersedes the earlier
statement that final target publication is unavailable. The local managed-host
identity model and external Git-server administration remain explicit boundaries.

Verification is underway; the
[implementation report](../plannings/migration-workflow-completion-implementation-report.md)
records measured gates and remaining real-application acceptance requirements.
The [current workflow guide](migration-workflow.md) describes owner preparation,
developer/reviewer sharing, trusted-terminal actions and GUI execution. No actual
Ember migration completion or live upstream protection is claimed.
