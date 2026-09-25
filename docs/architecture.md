# Architecture

## Current boundary

Phases 0 through 3 contain configuration, typed domain models, a CLI health check,
deterministic repository inventory, a read-only analysis agent, and typed migration planning
with 4-tier storage and approval signatures. The package uses a `src` layout so tests exercise
the installed package rather than importing directly from the checkout by accident.

```text
CLI/composition root
    -> PlanningService
        -> InventoryService
            -> FilesystemInspectorPort <- SafeFilesystemInspector
            -> FrameworkAdapterRegistry <- EmberClassicAdapter / AngularAdapter
        -> AnalysisService
            -> SnapshotFileReader
            -> AgentRuntimePort <- GeminiRuntimeAdapter (DEFAULT)
                                <- OpenAIAgentsRuntimeAdapter (PARALLEL)
                                <- FakeAgentRuntime (OFFLINE)
        -> RuleBasedPlanValidator
        -> CheckpointPort <- SqliteCheckpointStore (checkpoints.db)
        -> AuditLogPort <- SqliteCheckpointStore (audit.jsonl append mirror)
        -> GovernancePort <- GitGovernanceAdapter (.agent/)
    -> domain models (MigrationPlan, MigrationStep, ApprovalSignature)
```

The dependency direction points inward. `migration_agent.domain` may use Python and
Pydantic, but it must not import Typer, an agent SDK, filesystem code, persistence code, or
framework adapters. The CLI is an outer layer and may translate domain/application state
into terminal output and process exit codes.

## Deterministic inventory

`InventoryService` coordinates ports and contains no Ember or Angular branching. The
filesystem adapter walks entries in sorted order, refuses symlinks, junctions, and Windows
reparse points, resolves every eligible path beneath the selected root, bounds file sizes,
and reads only recognized text-file categories. Binary, oversized, ignored, unreadable,
outside-root, and secret-like entries are retained only as aggregate counts.

The generic inventory service parses supported `package.json` dependency sections and
recognizes package boundaries, including simple npm/yarn-style workspace globs. Invalid
manifests become typed non-fatal issues. Framework adapters consume the same bounded
snapshot and return confidence only when explicit evidence reaches their threshold.

Inventory models use repository-relative POSIX paths and sorted tuples. JSON uses sorted
keys and a schema version; Markdown is rendered from the same typed inventory. Reports are
written atomically to a directory that cannot overlap the source repository.

## Configuration

`Settings` reads explicitly named environment variables through `pydantic-settings`.
`AGENT_RUNTIME_PROVIDER` (default `gemini`), `AGENT_RUNTIME_MODEL`, and legacy `MIGRATION_AGENT_MODEL`
configure model selection. `AGENT_STATE_DIR` and `AGENT_MAX_STEP_FILES` configure state directory
and validator size limits. Configuration does not read or expose an API key.

## Agent runtime boundary

`AgentRuntimePort` defines the application boundary for analysis and planning:

```text
AgentRuntimePort
├── analyze(request: AnalysisRequest, file_reader: FileReaderPort) -> AnalysisResult
└── plan(request: PlanningRequest) -> list[MigrationStep]
```

The core domain and application layers remain strictly provider-neutral. Neither `google.genai`
nor `agents`/`openai` types cross into the domain or application services. Google Gemini is the
default configured provider via the official Google GenAI SDK; OpenAI is supported as a parallel
provider via the OpenAI Agents SDK; `FakeAgentRuntime` enables 100% offline verification. Remote
Agents SDK trace export is disabled by default.

The analysis agent interacts with the repository exclusively through bounded read-only tools:
`query_inventory` (accessing pre-built inventory data) and `read_repository_file` (accessing eligible
snapshot files with character and line boundaries). Post-generation evidence validation cross-references
all cited evidence paths against the deterministic inventory, marking any unverified references and
downgrading finding confidence.

## Planning & 4-tier storage topology (ADR-1, ADR-2)

Phase 3 introduces typed migration planning and the ADR-1 storage foundation:

1. **Git Governance (`.agent/`)**: Durable project governance stored in the target repository. Includes
   `.agent/manifest.json` (platform version and project metadata), `.agent/policy.json` (operational safety
   rules and protected paths), and `.agent/plans/<plan_id>.json` (exported migration plans).
2. **SQLite (`checkpoints.db`)**: Canonical local operational run state, idempotency tracking, and
   checkpoints (`plans`, `approvals`, `checkpoints`, `audit_events` tables).
3. **JSONL (`audit.jsonl`)**: Append-only audit stream mirror for human and external tool inspection.
4. **RFC 8785 Canonical Digests & Cryptographic Approval Binding**: Deterministic canonical JSON hashing
   (excluding volatile timestamps and status). `ApprovalSignature` cryptographically binds actor identity,
   the exact plan content digest, and the active project policy digest. Any modification to a plan or its
   underlying safety policy invalidates the approval token.

Source and staging repositories remain completely read-only throughout planning. No code transformations
occur until subsequent phases. Implementations and tests remain fully portable across Windows and Linux.

## Staging Workspace & Controlled Apply Protocol (ADR-8)

Phase 4 introduces isolated workspace staging and the ADR-8 controlled apply protocol:

1. **Workspace Boundary (`WorkspacePort`)**:
   - Manages isolated staging workspaces under user-data staging roots.
   - Enforces strict path containment and prevents overlapping paths between source and staging directories.
   - Disallows or skips symlinks resolving outside the repository root.
2. **Intermediate Component Representation**:
   - `IntermediateComponent` provides a framework-neutral structural model (name, tag name, inputs, reactive state properties, methods, templates, styles).
   - Source adapter `EmberClassicComponentExtractor` extracts presentational props, actions, and state.
   - Target adapter `AngularStandaloneComponentRenderer` renders modern Angular 17+ components conforming to strict project standards (`standalone: true`, `ChangeDetectionStrategy.OnPush`, signals, `@if` control flow, Bootstrap 5 utilities).
3. **ChangeSet & Dual Hashing**:
   - `ChangeSet` represents proposed file mutations (`CREATE`, `MODIFY`, `DELETE`) with POSIX paths and file modes (`0644`/`0755`).
   - File content is hashed with raw SHA-256 (`content_digest`).
   - ChangeSet metadata is digested canonically via RFC 8785 JSON formatting (`changeset_digest`), invariant to list permutation.
4. **ADR-8 4-Step Controlled Apply Protocol**:
   - **Base-State Binding & Drift Check**: Evaluates deterministic SHA-256 worktree fingerprint across all tracked files. If the target repository has drifted, enters `BaseChanged` and aborts apply before disk writes begin.
   - **Preflight Check**: Verifies repository path containment for all planned mutations.
   - **Backup Diff Snapshots**: Captures raw byte copies of all targeted files under `.agent-backups/<changeset_id>/`.
   - **Controlled Apply**: Applies patch mutations with explicit actor attribution and file mode preservation.
   - **Postcondition Validation**: Validates file presence, deletion, file modes, and SHA-256 content digests.
   - **Verified Rollback**: On any apply error, restores original files from backup snapshots and verifies restored state; transitions to `RolledBack`.
   - **Double-Fault State (`RecoveryRequired`)**: If rollback itself fails or leaves uncertain state, immediately halts and enters `RecoveryRequired`, preserving detailed diagnostic context for manual operator intervention.

## Allowlisted Validation & Bounded Repair Loop (Invariant 26)

Phase 5 introduces allowlisted validation and the Invariant 26 bounded self-repair loop:

1. **Command Runner Boundary (`CommandRunnerPort`)**:
   - `SubprocessCommandRunner`: Executes allowlisted subprocess commands strictly confined within a staging workspace.
   - Confinement controls: Fixed executable allowlist (`git`, `node`, `npm`, `npx`, `ng`, `tsc`, `pytest`, `python`, `uv`), `shell=False`, working directory confinement, and rejection of shell metacharacters (`;`, `&&`, `|`, `` ` ``, `$`, `\n`) in arguments.
   - Sanitization: Strips all API keys, secrets, tokens, and credentials from the subprocess environment.
   - Bounded execution: Configurable timeouts (SIGKILL on expiry) and bounded output truncation (64KB cap with full output SHA-256 digest).
   - `FakeCommandRunner`: Deterministic offline test double supporting canned results, configurable outcomes, and command execution tracking without subprocess spawning or network access.
2. **Validation Profiles**:
   - Target framework adapters (`AngularAdapter`, `EmberClassicAdapter`) own typed validation commands for profiles `LINT`, `TYPECHECK`, `TEST`, and `BUILD`.
   - `ValidationService` coordinates execution of validation suites against staging workspaces, logging structured audit events for every check.
3. **Bounded Repair Loop (`BoundedRepairService`)**:
   - Enforces Invariant 26: Maximum repair budget (default 3 attempts).
   - Each repair cites an extracted validation diagnostic and emits a **NEW** `ChangeSet` with a fresh `changeset_id` and fresh RFC 8785 `changeset_digest`.
   - Scope Containment: Verifies all repaired files are within the approved step scope; unapproved file modifications halt the loop immediately with status `DISALLOWED`.
   - Termination on repeated failure: Detects identical consecutive validation failures (matching diagnostic and output digest) and halts early rather than burning attempts without progress.
4. **Run Reporting (`ReportService`)**:
   - Compiles `MigrationRunReport` summarizing inventory, plan, applied changes, validation checks, repair history, and overall status (`SUCCESS`, `FAILED`, `ABORTED`).
   - Persists reports canonically in SQLite `run_reports` table, generates machine-readable JSON and readable Markdown tables, and logs `RUN_REPORT` audit events.

## Resumable Checkpoints, Audit Journal & Evaluations (Phase 6)

Phase 6 introduces crash-resilient operational state machines, deterministic audit logging, and repeatable offline evaluations:

1. **Resumable State Machine (`ResumableExecutionService`)**:
   - `RunRecord` persisted in SQLite `runs` table tracks lifecycle states (`INITIALIZED`, `STAGED`, `VALIDATING`, `REPAIRING`, `COMPLETED`, `FAILED`, `ABORTED`).
   - **Crash Recovery**: Resuming an interrupted run from `STAGED` or subsequent states verifies the intact staging workspace and skips staging materialization and component extraction, proceeding directly to validation.
   - **Budget Preservation Across Restarts**: When resuming during an interrupted repair loop, prior `REPAIR_ATTEMPT` checkpoints in SQLite are counted to compute the exact remaining attempt budget (`max_budget - prior_attempts`), preserving Invariant 26 guarantees.
   - **Idempotency on Completion**: Resuming an already `COMPLETED` run safely returns the terminal `MigrationRunReport` without re-executing steps.

2. **Deterministic Audit Redaction & Journal (`RedactionPolicy`, `audit.jsonl`)**:
   - `RedactionPolicy` recursively sanitizes dictionary keys matching sensitive substrings (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`, `AUTH`, `OPENAI`, `GEMINI`) and redacts inline token strings (`sk-*`, `bearer *`, `ghp_*`).
   - Payloads exceeding 512 bytes are digested with SHA-256 and truncated with size annotations to prevent log bloat.
   - Dual storage: Persisted canonically to SQLite `audit_events` and append-only mirrored to `audit.jsonl`.
   - **Chronological Verification (`verify_audit_log`)**: Uses physical database insertion order (`rowid`) rather than client timestamps to detect timestamp tampering or clock skew.

3. **Repeatable Offline Evaluation Harness (`EvaluationService`)**:
   - Computes precision, recall, and F1 scores against synthetic ground-truth benchmarks (`EvaluationBenchmark`, `EvaluationMetric`, `EvaluationResult`).
   - Filters out integration test fixtures (e.g. `tests/` directories and `*-test.js`) from production component discovery metrics.
   - Runs 100% offline without live API keys or external network dependencies.

4. **CLI Surface**:
   - `agent run [path] --plan <plan_id>`: Executes full migration with default-group dispatch.
   - `agent run list`: Lists all recorded migration runs from the local SQLite state store.
   - `agent run show <run_id>`: Displays run details, checkpoints count, and report status.
   - `agent run resume <run_id>`: Recovers and continues interrupted runs from the latest valid checkpoint.
   - `agent eval [fixture_path]`: Runs repeatable offline evaluation benchmark against synthetic fixtures.

## Extensibility & Second Reference Migration Pair (Phase 7)

Phase 7 introduces dynamic capability negotiation and demonstrates cross-framework extensibility without core refactoring (**ADR-3**):

1. **Framework Adapter Capability Negotiation (`FrameworkCapability`, `FrameworkCapabilities`, `NegotiationResult`)**:
   - Adapters explicitly declare typed capabilities: `INVENTORY`, `VALIDATION`, `SOURCE_TRANSFORMATION`, `TARGET_TRANSFORMATION`.
   - Adapters declare supported validation profiles (`LINT`, `TYPECHECK`, `TEST`, `BUILD`) and supported target framework identifiers (`supported_target_frameworks`).
   - `FrameworkAdapterRegistry.negotiate_pair(source_id, target_id)` negotiates end-to-end migration compatibility dynamically without hardcoded framework conditionals.
   - `get_supported_pairs()` enumerates valid source-to-target migration paths across all registered adapters.

2. **Second Reference Migration Pair: AngularJS Directive $\to$ Angular Standalone**:
   - **Source Adapter (`AngularJsDirectiveAdapter`)**: Detects AngularJS project evidence (`angular` in manifests, `.directive.js`, `ng-` template directives), provides allowlisted test validation commands, and declares source transformation capabilities targeting `angular`.
   - **Source Extractor (`AngularJsDirectiveExtractor`)**: Discovers directive files (`discover_components`), extracts isolate scope bindings (`@`, `=`, `&`, `<`) into typed inputs, extracts controller/link state properties into reactive state, and maps action methods.
   - **Target Renderer (`AngularStandaloneComponentRenderer`)**: Reused directly for AngularJS transformations, producing modern standalone TypeScript (`standalone: true`, `ChangeDetectionStrategy.OnPush`, signals `signal()`, inputs `input()`), modern templates (`@if` control flow, Bootstrap 5 utilities), component-scoped SCSS, and Jasmine/Jest `TestBed` specs.

3. **Core Transformation Decoupling (`TransformationService`)**:
   - Component discovery delegates to `extractor.discover_components(root)` rather than hardcoding repository file paths.
   - Dynamic negotiation: `TransformationService` can be initialized with `FrameworkAdapterRegistry` and `FilesystemInspectorPort` to dynamically negotiate extractors and renderers for any detected framework pair.
   - Core application services (`TransformationService`, `ValidationService`, `PlanningService`, `AnalysisService`, `EvaluationService`) remain 100% free of framework-specific `if/else` checks.

4. **Reusable Adapter Contract Tests (`test_framework_adapter_contract.py`)**:
   - Parameterized contract test suite running across all adapters (`EmberClassicAdapter`, `AngularJsDirectiveAdapter`, `AngularAdapter`).
   - Verifies protocol adherence, capability consistency, empty repository handling, validation command profiles, and transformation extractor/renderer boundaries.

## Specialist Agents Driven by Evaluation Evidence (Phase 8)

Phase 8 introduces specialized subagent personas driven by offline evaluation metrics, strictly maintaining centralized mutation authority and safety invariants (**ADR-6**):

1. **Specialized Subagent Roles (`SpecialistRole`, `SpecialistRuntimePort`)**:
   - **`Inventory Interpreter`**: Specializes in repository-level signal extraction, analyzing framework dependencies and package manifests to synthesize high-level architectural insights and migration strategies before detailed analysis.
   - **`Migration Analyst`**: Specializes in deep AST and code inspection on eligible files, producing structured findings without cluttering inventory or planner logic.
   - **`Plan Critic`**: Audits candidate migration plans before user review, checking for sequencing defects, missing prerequisites, and oversized file scopes (>10 files).
   - **`Repair Diagnostician`**: Diagnoses compiler, lint, and test failure outputs during the bounded self-repair loop to isolate the root cause and provide targeted repair guidance.

2. **Centralized Mutation Authority & Read-Only Safety**:
   - Subagents possess **zero** filesystem write permissions, zero command execution authority, and zero approval signing capability.
   - All mutations, staging operations, and command runs remain strictly centralized in core engine services (`TransformationService`, `BoundedRepairService`, `PlanningService`).

3. **Global Turn & Cost Budgets (`BudgetTracker`, `BudgetLimit`)**:
   - Global and per-role limits on turn counts (`max_total_turns`, `max_turns_per_role`), token limits (`max_total_tokens`), and dollar cost (`max_total_cost_usd`).
   - **Fail-Closed Enforcement**: If a subagent exhausts its allocated budget, the coordinator halts specialist invocation, logs a `SPECIALIST_BUDGET_EXCEEDED` audit event, and gracefully falls back to deterministic defaults.

4. **Deterministic Aggregation**:
   - **`DeterministicPlanCriticAggregator`**: Translates plan critique into deterministic plan modifications: flags steps, elevates step risks (`StepRisk.HIGH`), and withholds approval recommendation if critical issues exist. The critic cannot delete, insert, or reorder DAG steps directly.
   - **`DeterministicRepairDiagnosticianAggregator`**: Enforces **Invariant 26** scope boundaries. If the diagnostician recommends modifying a file outside the approved `allowed_scope`, the recommendation is deterministically rejected.

5. **Comparative Evaluation Evidence (`run_specialist_benchmark`, `SpecialistEvaluationMetric`)**:
   - Comparative benchmarking evaluates baseline accuracy against specialist-assisted workflows.
   - Telemetry tracks precision, recall, F1 score, plan critique scores, subagent turn consumption, and estimated cost across synthetic fixtures.




