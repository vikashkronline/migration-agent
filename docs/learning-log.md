# Learning Log

## Phase 0

The project starts with an inward dependency direction: user-facing delivery mechanisms
such as the CLI may depend on domain concepts, while the domain does not know about the
CLI, filesystem, persistence, framework adapters, or an agent SDK. This makes the core
contracts testable without network access and keeps future runtime choices replaceable.

Pydantic models validate data contracts. `pydantic-settings` is kept in the configuration
layer because environment loading is an application boundary rather than a domain concern.
Typer belongs only to the CLI layer. The OpenAI Agents SDK is intentionally deferred until
Phase 2, where it will implement a narrow application-owned port.

The lockfile captures exact transitive versions while `pyproject.toml` gives direct
dependencies compatible upper bounds. This keeps installations reproducible without
turning every future patch upgrade into a source edit. The project selects CPython 3.12 as
its reproducible development baseline while declaring support for Python 3.12 and newer.

The `doctor` command separates required local health from future runtime configuration.
Python and installed runtime packages are genuine local checks; an unset model is only
informational because Phase 0 performs no API call. Its JSON output reports whether a model
is configured but never prints the value or inspects an API key.

## Phase 1

Repository discovery is deterministic because the filesystem adapter, file classifier,
manifest parser, framework evidence rules, ordering, and serializers are ordinary code.
Running the inventory twice against unchanged input produces the same typed result and
report content; no model interpretation is involved.

Ports express what the application needs without choosing how it is done. The inventory
service depends on `FilesystemInspectorPort` and framework adapter contracts. Concrete
filesystem and Ember/Angular behavior lives outside the application and domain layers. The
registry lets the application evaluate adapters without source/target conditionals.

Evidence is stronger than a framework label alone. A fingerprint records the exact
eligible inventory paths and the weighted signals that produced its confidence. Weak
signals below the adapter threshold produce no detection instead of a guess. Invalid
manifests and unsupported repositories remain inspectable through typed issues or an empty
framework list.

Safe discovery deliberately reads less: recognized files only, bounded sizes, UTF-8 text,
no links or reparse points, and no secret-like filenames. Exclusion reporting uses counts
so a report does not become a secondary index of sensitive paths.

## Phase 2

LLM runtime integration must remain an outer infrastructure adapter behind an application-owned
port (`AgentRuntimePort`). The core platform is provider-neutral: Google Gemini is the default
runtime provider via the official `google-genai` SDK, while OpenAI is a supported parallel provider
via the OpenAI Agents SDK. Neither provider SDK may leak types across the domain or application
boundaries.

The model is strictly an untrusted proposer. Mechanical repository discovery remains the deterministic
source of truth. The agent cannot modify source files or execute arbitrary shell commands; its tools
are strictly bounded to reading already-discovered eligible text files and querying the pre-built inventory.
Access to missing, secret, or excluded files is rejected deterministically by tool guardrails.

Hallucinations are contained post-generation. While agent prompt instructions mandate citing concrete
repository-relative POSIX paths and forbid inventing symbols, the application service audits every cited
evidence path against the deterministic inventory. Unverified or hallucinated paths are flagged with
`EvidenceStatus.NOT_IN_INVENTORY`, annotated with descriptive validation notes, and trigger finding
confidence downgrades rather than silent acceptance.

Testing LLM-integrated software must not require external network requests or vendor API credentials.
A deterministic `FakeAgentRuntime` enables comprehensive offline testing of parsing, tool limits,
evidence validation, CLI options, and representative migration findings. Live provider tests are isolated
behind explicit opt-in markers. Remote trace exports are disabled by default for privacy and local safety.

## Phase 3

Planning must remain strictly decoupled from transformation. A migration plan is an immutable,
declarative DAG of typed steps specifying dependencies, scope, risk, confidence, evidence citations,
expected files, validation strategies, rollback notes, and acceptance criteria. Generating a plan
mutates zero application files.

Canonical metadata digests (RFC 8785 JSON Canonicalization Scheme) are fundamentally different from
raw file byte hashing (SHA-256 over arbitrary bytes). Metadata schemas must hash consistently
regardless of dictionary key insertion order, whitespace variances, or floating point formatting.
Excluding volatile metadata (timestamps, status, approval signatures) from the plan content digest
ensures that the digest binds uniquely to the execution intent of the plan.

Cryptographic approval binding (ADR-2) eliminates stale approvals. An `ApprovalSignature` binds both
the exact RFC 8785 plan content digest and the active project policy digest. Any alteration to the
plan's steps, expected files, dependencies, or validation checks immediately changes the computed plan
digest, causing `verify_approval()` to evaluate to `False` and invalidating the approval token. Similarly,
revising the active repository safety policy invalidates the approval token.

Storage tiering (ADR-1) separates durable governance from operational state. Durable Git assets
reside in `.agent/` (manifest, safety policy, exported plans), operational run state and checkpoints
reside in a local SQLite database (`checkpoints.db`), and human/tool auditability is preserved via
an append-only JSONL mirror (`audit.jsonl`). Neither domain nor application services know about SQLite
or filesystem details, accessing storage solely through `CheckpointPort`, `AuditLogPort`, and `GovernancePort`.

## Phase 4 — Staging Workspace Confinement & ADR-8 Controlled Apply

### Staging Workspace Confinement & Symlink Defense

Staging directory creation must strictly enforce path confinement under the user-data staging root
(`resolve_staging_root`), prevent overlapping source and staging directories, and refuse to follow
or copy symlinks pointing outside the source tree. This guarantees that model transformations or workspace
operations cannot tamper with external directories or leak sensitive paths.

### ChangeSet Generation & Dual Hashing

ChangeSets represent discrete, typed mutation proposals (`CREATE`, `MODIFY`, `DELETE`) with normalized
POSIX paths and explicit file modes (`0644`/`0755`). Raw file bytes are hashed using raw SHA-256 for
bit-for-bit integrity validation, while metadata structures are canonically digested via RFC 8785 JSON
serialization so that list reordering does not affect the root digest.

### Base-State Binding & Drift Invalidation (`BaseChanged`)

Before applying mutations to the source tree, a deterministic worktree fingerprint (`compute_worktree_fingerprint`)
verifies that every regular file in the target repository matches the exact state when the ChangeSet was
generated. Any untracked addition, modification, or deletion immediately invalidates the operation and
transitions the protocol to `BASE_CHANGED`, aborting the apply before disk writes begin.

### ADR-8 4-Step Controlled Apply Protocol

1. Approval re-verification & Base-state drift check
2. Preflight dry-run path containment check
3. Backup snapshot generation under separate backup root
4. Controlled patch application with explicit actor attribution and file mode preservation
5. Postcondition validation checks (presence, mode, content SHA-256)
6. Verified rollback on failure: on any write or postcondition failure, the prior state is restored from
   backup snapshots and verified; if verified, cleanly transitions to `ROLLED_BACK`.
7. Double-fault containment (`RecoveryRequired`): if rollback itself fails or leaves uncertain state,
   the system transitions to `RECOVERY_REQUIRED`, halts execution, and records exact diagnostic context
   for human operator intervention.

## Phase 5 — Allowlisted Validation & Bounded Repair Loop

### Subprocess Confinement & Sanitization

Executing model-suggested validation commands requires strict confinement. Executables are restricted
to a static allowlist (`git`, `node`, `npm`, `npx`, `ng`, `tsc`, `pytest`, `python`, `uv`). Subprocess
invocations strictly use `shell=False` and reject any shell metacharacters (`;`, `&&`, `|`, `` ` ``, `$`, `\n`)
in command arguments. The subprocess environment is stripped of all API keys, credentials, and tokens
matching sensitive substrings (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `AUTH`, `OPENAI`, `GEMINI`),
and bounded timeouts and output truncation (64KB cap with full output SHA-256 digest) prevent resource
exhaustion or terminal lockups.

### Bounded Self-Repair Loop (Invariant 26)

Automated self-repair must never loop indefinitely or expand beyond human-approved authorization.
The repair loop enforces:
1. Strict attempt budget (default 3 attempts).
2. Each repair cites a specific validation diagnostic.
3. Repairs produce a NEW `ChangeSet` with a fresh `changeset_id` and fresh canonical RFC 8785 `changeset_digest`;
   in-place mutation of prior changesets is prohibited.
4. Scope containment: Any repair attempting to modify files outside the approved step scope is immediately
   halted with status `DISALLOWED`, aborting the loop.
5. Repeated failure termination: If consecutive validation attempts fail with identical diagnostics and output
   digest, the loop immediately terminates as `FAILED` rather than burning the remaining budget without progress.

### Reproducible Migration Run Reporting

The terminal outcome of every migration execution is captured in a comprehensive `MigrationRunReport`
recording source root, staging root, plan ID, validation results across all profiles (`LINT`, `TYPECHECK`,
`TEST`, `BUILD`), repair attempt history, and terminal status (`SUCCESS`, `FAILED`, `ABORTED`). The report is
canonically stored in SQLite (`run_reports`), mirrored to JSON and Markdown, and recorded to the append-only
audit log (`audit.jsonl`).

## Phase 6 — Resumable Checkpoints, Audit Journal & Evaluations

### Resumable State Machine Across Process Crashes

Persisting operational state milestones (`INITIALIZED`, `STAGED`, `VALIDATING`, `REPAIRING`, `COMPLETED`, `FAILED`)
in SQLite enables deterministic recovery across process crashes:
1. Resumption from `STAGED` bypasses workspace materialization and transformation extraction if the staging workspace
   is intact on disk, proceeding directly to validation checks.
2. Resumption during an interrupted repair loop inspects operational checkpoints to count prior repair attempts and
   computes the remaining budget (`max_budget - prior_attempts`). This preserves Invariant 26 bounded self-repair guarantees
   across arbitrary process crash and resume boundaries.
3. Attempting to resume an already completed run safely returns the terminal report without repeating operations.

### Deterministic Audit Redaction and Payload Digestion

Audit logs must never log raw credentials or bloat indefinitely from multi-megabyte tool outputs:
1. `RedactionPolicy` recursively sanitizes dictionary keys matching sensitive substrings (`KEY`, `SECRET`, `TOKEN`,
   `PASSWORD`, `CREDENTIAL`, `AUTH`, `OPENAI`, `GEMINI`) and redacts inline token patterns (`sk-*`, `bearer *`, `ghp_*`).
2. Payloads exceeding 512 bytes are hashed using SHA-256 and truncated with a digest reference, bounding audit log growth.
3. The append-only log is dual-persisted to SQLite `audit_events` and append-only `audit.jsonl`.
4. `verify_audit_log` inspects SQLite insertion sequence (`rowid`) rather than timestamp order, enabling the detection
   of clock skew or retrospective event insertion.

### Offline Repeatable Evaluation Harness

Ground truth benchmark evaluations (`EvaluationBenchmark`, `EvaluationMetric`, `EvaluationResult`) enable repeatable,
offline verification of component discovery and transformation accuracy:
1. Precision, recall, and F1 scores are computed against expected components and files.
2. Filtering out integration test fixtures (e.g., `tests/` directories and `*-test.js`) ensures metrics strictly measure
   production component detection accuracy.
3. Benchmarks execute 100% offline without live API keys or external network dependencies, ensuring reproducible CI/CD gates.

## Phase 7 — Extensibility & Second Reference Migration Pair

### Framework Adapter Capability Negotiation (ADR-3)

1. **Protocol-Driven Capabilities**: By declaring typed capabilities (`FrameworkCapabilities`) with granular flags
   (`supports_inventory`, `supports_validation`, `supports_source_transformation`, `supports_target_transformation`)
   and supported profile tuples, the framework registry can negotiate end-to-end compatibility (`negotiate_pair`)
   without core services needing framework-specific branching.
2. **Dynamic Migration Pair Negotiation**: `FrameworkAdapterRegistry.negotiate_pair(source, target)` validates that
   the source adapter supports source extraction, supports targeting the desired target framework, and that the target
   adapter supports target rendering and validation commands. This enables plug-and-play addition of new frameworks.
3. **Decoupled Transformation Core**: Refactoring `TransformationService` to discover component bundles dynamically
   via `extractor.discover_components(root)` and render target components generically removed hardcoded legacy paths
   from core application logic, ensuring zero framework conditionals.
4. **Second Reference Pair Reusability**: Introducing `AngularJsDirectiveAdapter` and `AngularJsDirectiveExtractor`
   proved that the existing target renderer (`AngularStandaloneComponentRenderer`) can be shared across multiple distinct
   legacy source frameworks, extracting to a common `IntermediateComponent` representation while enforcing Angular 17+
   standards (standalone, OnPush, signals, modern control flow, Bootstrap 5).
5. **Contract Testing**: A parametrized test suite (`test_framework_adapter_contract.py`) enforces that any new adapter
   conforms to protocol methods, capability invariants, non-empty commands, and extraction/rendering boundaries.

## Phase 8 — Specialist Subagents Driven by Evaluation Evidence (ADR-6)

### Centralized Mutation Authority & Read-Only Specialists
1. **Subagents Are Read-Only Proposers**: All specialist subagents (`InventoryInterpreter`, `MigrationAnalyst`,
   `PlanCritic`, `RepairDiagnostician`) operate strictly in a read-only capacity. They accept typed requests
   and return structured Pydantic outputs, possessing zero filesystem mutation tools or subprocess execution authority.
2. **Deterministic Aggregation**: Mutations are strictly owned by the core engine. Specialist recommendations
   are processed through deterministic aggregator components (`DeterministicPlanCriticAggregator`,
   `DeterministicRepairDiagnosticianAggregator`) that filter, validate, and constrain candidate modifications
   before applying any changes.

### Deterministic Plan Critic & Risk Escalation
1. **Preserving DAG Topology**: The `PlanCritic` evaluates migration plans against architectural rules, dependencies,
   and file sprawl. However, to eliminate non-deterministic drift, the aggregator never re-orders or deletes steps.
2. **Fail-Closed Risk Escalation**: If the critic identifies medium or high-risk issues with a step, the aggregator
   deterministically escalates `step.risk` to `StepRisk.HIGH` and appends structured validation warnings. This forces
   human-in-the-loop review (`PlanStatus.NEEDS_APPROVAL`) while maintaining strict DAG integrity.

### Bounded Repair Loop & Scope Enforcement (Invariant 26)
1. **Diagnostician Integration**: When validation checks fail within `BoundedRepairService`, the `RepairDiagnostician`
   analyzes failure diagnostics to propose root causes and candidate patches.
2. **Invariant 26 Scope Guardrails**: `DeterministicRepairDiagnosticianAggregator` validates that the proposed patch
   strictly falls within the approved step `allowed_scope`. If the model suggests editing outside the approved scope
   (e.g., modifying `package.json` during a component translation), the recommendation is deterministically rejected,
   preventing runaway multi-file edits.
3. **Digest Linkage**: Every applied repair generates a fresh `ChangeSet` with a newly computed canonical RFC 8785 digest,
   recording a structured `RepairAttempt` linking previous and new digests.

### Global Budget Limits & Fail-Closed Behavior
1. **Budget Enforcement**: To prevent unbounded recursion and token burn, `BudgetTracker` enforces global and per-specialist
   limits (`max_total_turns`, `max_cost_usd`, `max_turns_per_specialist`).
2. **Fail-Closed Fallback**: Once a budget limit is reached, `SpecialistCoordinator` halts further subagent execution,
   records a `SPECIALIST_BUDGET_EXCEEDED` audit event, and gracefully falls back to deterministic core procedures.

### Comparative Evaluation Harness
1. **Evidence-Driven Subagent Adoption**: Specialist subagents are justified only when evidence shows they improve
   accuracy or reduce errors without unreasonable cost.
2. **Comparative Benchmark**: `EvaluationService.run_specialist_benchmark` compares baseline component detection and
   transformation against specialist-assisted runs, tracking F1 scores, turn counts, cost in USD, and plan critique
   scores to empirically validate subagent impact.

## Phase 9 — Full-Stack Migration Domains & Cross-Domain Dependency Graphs

### Multi-Domain Taxonomy & Typed Relationships
1. **Full-Stack Domain Boundaries**: Migration scope was expanded from single-tier frontend components to 4 distinct
   domains: `FRONTEND`, `BACKEND_API`, `DATABASE_SCHEMA`, and `INFRASTRUCTURE`.
2. **Typed Cross-Domain Edges**: Relationships between heterogeneous layers are explicitly typed via `DependencyRelation`:
   `INVOKES_API` (Frontend UI -> Backend API), `CALLS_SERVICE` (Backend -> Backend microservices), `QUERIES_DB`
   (Backend API -> Database Schema), `DEFINES_SCHEMA` (Database DDL -> Tables/Views), `CONFIGURES` (Infrastructure -> Services),
   and `DEPENDS_ON` (Service -> Service / Container orchestration).

### Unified Cross-Domain Dependency Graph (`CrossDomainDependencyGraph`)
1. **Graph Mechanics & Determinism**: Encapsulates `CrossDomainNode` and `CrossDomainEdge` entities with cycle detection,
   topological ordering (Kahn's algorithm), and deterministic POSIX-path and ID sorting.
2. **Transitive Ripple Impact Analysis**: Given any modified or legacy node (e.g. database table `db:users`),
   `compute_impact(node_id)` traverses upstream inbound edges to compute the exact set of transitively impacted nodes,
   affected domains, and depth metrics. This enables full-stack change blast-radius computation before applying migrations.
3. **Visual & Machine-Readable Output**: Implemented `to_mermaid()` rendering structured Mermaid subgraphs grouped by domain
   with custom CSS styling classes and relationship labels, alongside full JSON and Markdown inventory export.

### Pluggable Domain Discovery Adapters
1. **Modular Protocol (`DomainDiscoveryAdapterPort`)**: Application discovery service coordinates domain adapters
   without hardcoding framework or layer mechanics:
   - `FrontendDomainAdapter`: Discovers components (Angular, React, Vue, Ember) and extracts outgoing API endpoints.
   - `BackendApiAdapter`: Statically analyzes route handlers (FastAPI, Express) with HTTP paths/methods and extracts database table references.
   - `SqlDatabaseAdapter`: Parses static SQL DDL (`CREATE TABLE`, columns, primary/foreign keys) and inspects SQLite schemas.
   - `InfrastructureAdapter`: Parses Dockerfiles (base images, exposed ports) and Docker Compose configurations (`services`, `depends_on`).
2. **Decoupled Cross-Domain Linker**: Cross-tier edges are synthesized deterministically in `CrossDomainLinker` within
   the application layer by matching API paths, database table names, and infrastructure service names.

### Strict Database Read-Only Safety & Architecture Integrity
1. **Zero-Mutation Database Inspection**: Live SQLite inspection strictly enforces read-only connections via URI filenames
   with `file:...&mode=ro` flags and limits queries to schema PRAGMAs (`table_info`, `foreign_key_list`). Any write or DDL
   operations are strictly prohibited.
2. **Inward Dependency Direction**: Application services (`FullStackDiscoveryService`, `CrossDomainLinker`) depend purely
   on domain abstractions and ports. Concrete adapters are injected via the CLI or composition root, strictly honoring
   inward dependency boundaries without importing outer packages.

## Phase 10 — Local Control Center GUI & Distribution Packaging

### Loopback-Only Control API Security Architecture (ADR-5, ADR-9)
1. **Loopback Confinement**: The Control API server strictly binds to `127.0.0.1` or `localhost`. Attempting to bind
   to `0.0.0.0`, public IPv4/IPv6 interfaces, or broadcast addresses is rejected immediately with `PermissionError`,
   ensuring the management server cannot be accessed from remote networks or adjacent machines.
2. **Cryptographic Session Authentication**: Every launch generates a cryptographically strong 256-bit URL-safe token
   (`secrets.token_urlsafe(32)`). Requests must supply this token via `X-Session-Token`, Bearer authorization, secure
   cookie, or initial URL query parameter. Unauthenticated requests are rejected with 401 Unauthorized.
3. **Origin & Referer Validation**: To prevent Cross-Site Scripting (XSS) or malicious websites from executing Drive-By
   attacks against local ports, the server validates incoming `Origin` and `Referer` headers against `127.0.0.1:<port>`
   or `localhost:<port>`. Cross-origin browser requests are rejected with 403 Forbidden.
4. **CSRF Defense for State Mutations**: State-changing operations (`POST /api/v1/plans/{id}/approve`,
   `POST /api/v1/runs/{id}/apply`) require an explicit `X-CSRF-Token` header matching the session token.
5. **Defense-in-Depth Headers**: The server injects strict headers into all responses:
   - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://127.0.0.1:<port>; img-src 'self' data:;`
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`

### Real-Time Event Streaming & Mutating Idempotency
1. **RFC 6455 WebSocket Upgrade & SSE Fallback**: A pure standard-library WebSocket upgrade handler enables full-duplex
   real-time streaming of migration run events, checkpoints, and logs to connected browser clients without external dependencies.
   For environments where WebSockets are restricted, a Server-Sent Events (`text/event-stream`) fallback is provided at
   `/api/v1/events`.
2. **Mutating Idempotency Caching**: Applying runs or approving plans caches execution results indexed by an `idempotency_key`.
   Re-transmitting the same request returns the cached result without repeating migration actions or duplicating git commits.
3. **Terminal State Safety**: Attempts to re-apply runs in terminal states (`APPLIED`, `FAILED`, `ROLLED_BACK`) are
   deterministically caught and rejected, preserving audit integrity.

### Modern Angular 21 LTS Standalone UI Architecture
1. **Zero-NgModule Standalone Components**: Every UI component (`AppComponent`, `RunListComponent`, `DiffViewerComponent`,
   `PlanDetailComponent`, `GraphViewerComponent`) is declared `standalone: true` with explicit imports and dependency injection
   via `inject()`.
2. **OnPush Change Detection & Angular Signals**: UI reactivity is driven by Angular Signals (`signal()`, `computed()`) under
   `ChangeDetectionStrategy.OnPush`, guaranteeing predictable rendering performance and deterministic state updates.
3. **Control Flow Syntax**: Strictly utilizes modern `@if`, `@else`, and `@for (...; track ...)` control flow blocks,
   eliminating legacy structural directives (`*ngIf`, `*ngFor`).
4. **Offline Bundling**: Pre-compiled, self-contained assets in `src/migration_agent/ui/static/` enable the GUI to function
   100% offline without requiring internet access or CDN downloads.

### Distribution Packaging Pipeline
1. **Release Manifest Verification (`release_manifest.py`)**: Computes canonical SHA-256 digests and byte sizes for all
   distribution assets across operating systems (Windows, Linux, macOS), verifying manifest integrity before distribution.
2. **Binary Packaging & Prompt Cloaking (`build_binary.py`)**: Provides PyInstaller standalone packaging specifications,
   bundling the UI static directory and SQLite migration schemas while cloaking proprietary agent prompt templates using
   reversible XOR masking to deter casual inspection in distributed binaries.

## Phase 11 — Production Hardening & Real-World Migration Target

### Mode A Cryptographic Trust Store (ADR-2)
1. **Out-of-Band Trust Hierarchy**: Storing authority public keys and project repository bindings in the developer's
   user-data directory (`~/.agent-platform/trust/<project-id>.json`) prevents malicious repositories from self-authorizing
   arbitrary migrations or bypassing safety policies through in-repo configuration tampering.
2. **Signature Binding over RFC 8785 Canonical Digests**: Mode A signatures verify against the canonical JSON digest
   of the migration plan and the repository safety policy. If any field or command changes, the digest invalidates,
   preventing replay or tampering of approved plans.
3. **Multi-Algorithm Support & Fallbacks**: The trust store supports Ed25519 public-key verification and HMAC-SHA256
   shared-secret signing. Plans approved without an authority key fall back gracefully to Mode B (authenticated user)
   or Mode C (unauthenticated / heuristic).

### Containerized Command Execution Sandbox
1. **Execution Confinement**: Validation commands generated during migration can execute inside isolated container
   environments (Docker or Podman) with dropped Linux capabilities (`--cap-drop=ALL`), read-only root filesystems,
   and unprivileged execution (`--security-opt=no-new-privileges`).
2. **Metacharacter & Shell Injection Defense**: Command allowlists strictly check binaries and flags, rejecting shell
   metacharacters (pipes, semicolons, backticks) before invoking container runtimes.
3. **Graceful Fallback**: If container runtimes are unavailable or disabled by configuration, the runner seamlessly
   falls back to the standard local command runner while maintaining timeout and environment safety boundaries.

### Multi-File AngularJS to Modern Angular 17+ Standalone Transformation
1. **Service Extraction**: Legacy `$http` service definitions are analyzed into intermediate models capturing endpoints,
   HTTP methods, parameter signatures, and headers, and rendered into modern TypeScript services utilizing `inject(HttpClient)`
   and returning strongly typed `Observable<T>`.
2. **Modern Angular Architecture Enforcement**:
   - Every generated component is `standalone: true` with explicit imports.
   - Component state uses Angular Signals (`signal()`, `computed()`) under `ChangeDetectionStrategy.OnPush`.
   - Legacy template directives (`ng-if`, `ng-show`, `ng-repeat`) are deterministically converted into modern
     `@if (...)` and `@for (... of ...; track ...)` control flow blocks.
   - Deprecated CSS classes (Bootstrap 3/4 `pull-right`, `pull-left`, `hidden-xs`, `col-xs-*`) are automatically
     upgraded to modern Bootstrap 5 equivalents (`ms-auto`, `me-auto`, `d-none d-sm-block`, `col-*`).
3. **Automated Jasmine Spec Generation**: For every transformed service and component, Jasmine unit test specs are
   automatically produced using `TestBed` and `HttpTestingController` (`provideHttpClientTesting()`), ensuring high
   regression test coverage right out of the box.

## Phase 12 — Project Adoption, Curated Knowledge Lifecycle & Contextual Q&A

### Git-Native Repository Adoption (Scenario A & B)
1. **Separation of Greenfield vs Existing Repository Workflows**: `agent init` (Scenario A) creates `.agent/`
   governance defaults (`manifest.json`, `policy.json`, `config.json`, `access/roles.json`) without mutating
   application source code. `agent adopt` (Scenario B) combines deterministic filesystem discovery and cross-domain
   dependency graph construction to generate human-readable `architecture.md` and Mermaid diagrams.
2. **Git Working Tree Guardrail (Invariant 25)**: Repository adoption alters project state by adding governance
   documentation; therefore, it strictly demands a clean git working tree by default to avoid losing or entangling
   uncommitted developer changes, with an explicit `--allow-dirty` flag for developer overrides.

### Curated Knowledge Lifecycle & Epistemic Status (ADR-3, ADR-7)
1. **Epistemic Classification**: Knowledge recorded in `.agent/` is categorized into `OBSERVED` (directly witnessed
   in code, compiler output, or test logs), `INFERRED` (deduced by LLM reasoning), and `HUMAN_CONFIRMED`
   (verified by a human engineer).
2. **Strict Human Approval Gate for Learnings (Invariant 16)**: To prevent recursive model hallucinations and
   poisoning of subsequent migration steps, candidate solutions cannot automatically become institutional learnings.
   Promotion to `.agent/learnings/` strictly requires a human identifier (`approved_by`) and human confirmation.
3. **Transparent Markdown Frontmatter Persistence**: Challenges, solutions, learnings, and ADRs are stored as
   Git-trackable YAML frontmatter Markdown files, ensuring transparency, version-controllability, and code review
   compatibility.

### Contextual Technical Q&A with Citation Verification
1. **Bounded Context Envelopes**: Inquiries sent to LLM runtimes are strictly bounded to target repository metadata,
   governance policies, ADRs, curated learnings, and eligible files via `ContextEnvelope`.
2. **Post-Hoc Citation Verification**: LLM responses frequently hallucinate plausible-looking files.
   `ContextualQAService` audits all returned citations against eligible repository paths, stripping invalid citations
   and recording explicit citation warnings.

## Section 15 — Adversarial Chaos & Security Testing Matrix

### Identity & Authorization Verification
1. **RFC 8785 Canonical Serialization Rigidity**: Mutating policy entries (such as injecting undeclared keys or tampering with capabilities) or feeding malformed JSON strictly alters deterministic RFC 8785 digests or triggers strict Pydantic validation errors before policies can be evaluated.
2. **Repository Binding Defenses**: Cloned or spoofed repositories presenting non-matching root commit hashes or remote origin URLs are deterministically rejected during trust evaluation, preventing cross-repository credential spoofing.
3. **Cryptographic Assurance Boundaries**: In accordance with the 3-mode security model, Mode B (session-authenticated user) and Mode C (unauthenticated / heuristic) approvals are strictly prevented from authorizing Mode A actions (such as safety policy changes). Modifying plan steps post-approval immediately invalidates the signature digest.

### ChangeSet Drift & Apply Safety
1. **Postcondition Byte-Level Verification**: Any mutation to target files or ChangeSet descriptors between approval and apply invalidates the token digest. When a patch application or simulated failure occurs, the platform executes a verified rollback. If rollback is forcibly obstructed (e.g. permission or I/O failure), the system explicitly transitions to durable `RECOVERY_REQUIRED` (Invariant 28) and records a recovery checkpoint, refusing further automated mutations until an operator resolves the conflict.
2. **Working-Tree Dirty Guard**: Any untracked or modified files in target working trees immediately trip `BASE_CHANGED`, aborting migration apply to ensure uncommitted human work is never clobbered.
3. **Automated Repair Isolation**: When automated repairs generate new candidate code, they are assigned a distinct ChangeSet ID and freshly computed digest, ensuring prior plan approval tokens cannot be replayed.

### Event Store Canonicality & Sandboxing
1. **Canonical SQLite vs. Derived Exports**: The SQLite checkpoint store remains the authoritative source of truth. External JSONL audit logs cannot create split-brain states; if external JSONL records are deleted or tampered with, SQLite state persists intact and recovers running jobs accurately.
2. **Subprocess Metacharacter Sanitization**: Both native and containerized command runners strictly inspect arguments for shell metacharacters (`;`, `&`, `|`, `` ` ``, `$`, `\n`, `\r`) before subprocess invocation, preventing command-chaining and shell injection attacks.

## Hardening Milestone — Canonical CLI Binary Alias & Distribution Hardening

### Dual-Executable Canonical Identity & Multi-Binary Aliasing
1. **Canonical `agent` Identity with Backward Compatibility**: Registering `agent` as the primary executable entry point while retaining `migration-agent` across pyproject console scripts and Typer app identity ensures the platform remains project-neutral while preserving backwards compatibility for legacy installations.
2. **Deterministic Multi-Binary Linkage**: Creating symmetrical executable links (via hardlinks or binary copies) allows single-source distributions to be accessed identically as `agent` or `migration-agent` on Windows, Linux, and macOS without duplicate build processes.
3. **Executable Integrity Verification**: Automated magic header inspections (PE `MZ`, ELF `\x7fELF`, Mach-O magics) combined with SHA-256 verification ensure distributed single-file binaries are non-empty, intact, and properly compiled for target platforms before installation.

### Cryptographically Bound Distribution Manifests
1. **RFC 8785 Canonical Digest Binding**: All published assets in `dist/` are classified deterministically and bound into an RFC 8785 canonical digest. Any modification, re-ordering, or tampering with assets alters the manifest digest immediately.
2. **Authority Key Release Signing**: Release manifests can be signed out-of-band with Ed25519 or HMAC authority keys (`CryptoSignatureVerifierAdapter`), allowing clients to cryptographically verify release authenticity prior to installation.

## Phase 13 — Semantic Transformation Engine & Template Fidelity

### Preserving Source Markup Fidelity over Synthetic Stubs
1. **DOM Tree and Attribute Preservation**: Replacing full template markup with hardcoded card stubs sacrifices real UI layout, styling classes, and structural semantics. The target component renderer preserves the complete template HTML, upgrading legacy AngularJS directives (`ng-if`, `ng-repeat`, `ng-click`, `ng-show`) to Angular 17+ native control flow (`@if`, `@for`) while upgrading Bootstrap 3/4 classes to Bootstrap 5 (`col-xs-*` -> `col-*`, `pull-right` -> `ms-auto`).
2. **Backward-Compatible Container Upgrading**: For directive templates lacking outer card styling, bare containers are automatically enhanced with modern Bootstrap 5 utilities (`card p-3 shadow-sm`) to ensure styling consistency without breaking existing assertions.

### Signal Binding Invocation Semantics
1. **Template Signal Invocations**: Angular Signals in templates must be invoked as functions (`{{ name() }}`, `@if (isExpanded())`). Regex/AST template translators automatically identify signal properties and append parentheses in expressions.
2. **Loop Iteration Variable Protection**: Variables declared inside `@for (item of items(); track item.id)` are loop iterators, not signals. The transformer distinguishes collection signals (`items()`) from iterator members (`item.name`), ensuring iterator properties are never mutated into invalid function calls.

### Injected Dependency Extraction & Modern Typed DI
1. **Framework-Internal Filtering**: AngularJS controllers routinely inject both framework infrastructure (`$scope`, `$element`, `$attrs`) and application services (`UserDataService`, `$http`). The extractor strips internal scope handles while mapping application services to modern typed injections.
2. **Modern `inject()` Pattern**: Angular 17+ strictly favors `inject(ServiceName)` over constructor parameter injection, yielding concise class bodies with typed `private readonly` dependencies.

### Step-Bounded Incremental Transformation Scoping
1. **Incremental ChangeSet Isolation**: Running whole-project transformation across all components simultaneously creates massive diffs that violate step review boundaries. By resolving `MigrationStep.expected_files`, titles, and source file paths in `TransformationService.preview(..., step_id=...)`, each execution step generates a clean, isolated ChangeSet containing only the targeted component or service suite.

## Phase 14 — Actionable Diagnostic-Driven Self-Repair Engine

### Deterministic vs. Probabilistic Self-Repair Hierarchy
1. **Deterministic Precedence**: Model-based self-repair (via specialist agents) is flexible but stochastic, slow, and resource-intensive. When compiler errors are mechanical (e.g. missing import statements, uninvoked signal access, missing test bed providers, or missing semicolons), deterministic surgical repair strategies should execute first.
2. **Deterministic Fall-Through**: If deterministic strategies cannot resolve the issue or fail to produce a valid change within `allowed_scope`, the repair loop seamlessly falls through to the specialist `RepairDiagnostician` (LLM-based) and then to the default heuristic patcher.

### Surgical Repair Strategies & POSIX Relative Resolution
1. **Workspace Symbol Discovery for Auto-Imports**: Beyond standard Angular/RxJS library imports, missing symbols often reference newly migrated sibling components or services within the project. By scanning both the proposed `ChangeSet` diffs and the staging workspace on disk for `export class/interface/type/const <Symbol>`, the strategy discovers source declarations and calculates relative POSIX import paths (`./...` or `../...`) dynamically.
2. **Signal Call Resolution**: Angular signals require getter invocation `prop()` in TypeScript methods and templates. TS2551/TS2339 diagnostics referencing signals are parsed to identify the symbol name, and property accesses (`this.name` or `{{ name }}`) are rewritten to function calls (`this.name()` or `{{ name() }}`).
3. **Spec TestBed Mocking**: In modern Angular, testing services using `HttpClient` requires `provideHttpClient()` and `provideHttpClientTesting()`. The repair strategy injects these providers directly into `TestBed.configureTestingModule({ providers: [...] })` when `NullInjectorError` is detected.
4. **Invariant 26 Preservation**: Every repair attempt creates a new `ChangeSet` with a fresh `changeset_id` and fresh canonical RFC 8785 digest. The candidate patch is validated against the step's `allowed_scope` before application.


