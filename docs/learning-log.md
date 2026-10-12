# Learning Log

## 2026-10-07 — Common Control Center and canonical evidence

A generic navigation shell can consume current migration workflows without making
frameworks part of its application query model. Missing project-readiness entities
must stay unknown; folder existence and run counts cannot stand in for feature
acceptance. Transaction-scoped invalidation makes independent CLI/MCP updates
visible without trusting a process-local broadcast as durable truth.

Approval links must pin the artifact, and confirmations must pin their selected
detail. Browser/session authentication cannot replace human approval. Replaying a
request should recover its durable receipt, not execute a source change again.
Angular's HTML sanitizer removes SVG: strict Mermaid output displayed as an image
keeps diagrams usable without bypassing document-HTML sanitization or enabling
interactive callbacks. Visual inspection also caught Angular's optimized stylesheet
loader using an inline `onload` blocked by CSP. Disabling critical-CSS inlining
preserves the script policy; tests must assert actual responsive visibility and
rendered theme, not merely working click handlers and theme attributes.

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

## Phase 15 — Streamlined Migration Pipeline & Semantic Evaluation

### Unified Migration Pipeline Orchestration (`MigrationPipelineService`)
1. **End-to-End Coordination Without Abstraction Leaks**:
   `MigrationPipelineService` coordinates the full lifecycle: preflight checks -> Git clean working tree verification (Invariant 25) -> `.agent/` governance adoption validation -> DAG plan generation -> Mode B cryptographic sign-off -> isolated staging workspace materialization -> allowlisted validation with bounded self-repair -> ADR-8 4-step controlled apply with verified backup/rollback -> dual-tier reporting (human markdown + machine JSONL). Application services strictly maintain inward dependencies, taking needed ports and services via dependency injection rather than importing concrete infrastructure adapters.
2. **Deterministic Working Tree Guardrails & Overrides**:
   Applying changes to a dirty git working tree risks clobbering untracked human modifications or entangling migration diffs with unrelated working state. The pipeline enforces clean working trees by default, providing explicit `--allow-dirty` overrides for local test runs.
3. **Dry-Run & Step-Wise Review Safeguards**:
   The unified pipeline honors `--dry-run` to preview generated `ChangeSet` proposals without staging execution or disk writes, and `--step` to execute one plan step at a time, keeping changes reviewable and granular.

### Semantic Evaluation & Structural Fidelity Benchmarks
1. **Beyond Pure String Diffing**:
   Traditional migration evaluation relied on token overlap or exact character diffs against ground truth stubs, which falsely penalized valid code structural improvements (such as adding Bootstrap 5 utility classes or formatting differences). Semantic evaluation assesses migration output through three deterministic quality pillars:
   - `compilation_pass_rate`: Validates that migrated TypeScript and HTML files have balanced structural delimiters (curly braces, parentheses, angle brackets) and declare valid standalone component or class exports.
   - `spec_pass_rate`: Measures Jasmine/Karma test completeness by verifying the presence of `describe`, `it`, `expect`, and `TestBed` configuration blocks.
   - `control_flow_fidelity`: Quantifies modernization fidelity by measuring the ratio of Angular 17+ control flow blocks (`@if`, `@for`, `@switch`) versus legacy AngularJS directives (`ng-if`, `ng-repeat`, `ng-show`, `*ngIf`).
2. **Targeted Specialist Benchmark Harnesses**:
   The evaluation service supports running benchmarks with `--semantic` flags across all adapters or specialized agent teams, producing structured reports with clear pass/fail status against defined thresholds (`min_compilation_rate`, `min_spec_rate`, `min_fidelity`).




## 2026-10-04 — Phase 16 remediation and remaining implementation

A static executable template does not isolate code invoked by npm scripts. Host validation therefore fails closed unless a preinstalled pinned container image is configured. Plan signatures cannot stand in for exact ChangeSet approvals. Approval records and backups belong outside source Git; repaired bytes invalidate provenance. A TTY alone cannot prove human intent against arbitrary same-account automation, so Mode B trust is documented and Mode A signers must remain human-controlled. Client configuration documentation does not establish real IDE interoperability.

Live standalone repair must pass the same typed proposal gate as host repair,
rather than mutating an existing approved staging artifact. Provider guidance is
restricted to recognized deterministic strategies; unsupported guidance stops.
Ordinary CLI/MCP startup now imports provider SDKs only on provider selection.
The earlier Phase 15 description of automated Mode B sign-off does not authorize
Phase 16 source apply; exact artifact review is a separate human action.

## 2026-10-05: native validation consent and evidence

Docker-free Windows validation requires an explicit account-execution trust
decision separate from exact source approval. Fixed direct Node entry points
avoid top-level command wrappers; npm scripts still need the verified Windows
command processor in the fresh environment. Atomic job assignment closes the
suspended-process orphan window. Provenance and consent are rechecked at apply;
fake and legacy evidence require revalidation. [Operations](native-validation.md).

## 2026-10-05: browser evidence is a separate mandatory gate

Command success does not establish UI quality. Real viewport/state screenshots,
DOM/ARIA facts and complete rule verdicts are now bound to the staged build and
checked at source approval. Repairs create new artifacts and new capture; optional
E2E runs last. Chromium needs non-secret Windows known-folder metadata even when
its browser profile and temporary storage remain fresh. External visual-provider
transfer was initially blocked pending explicit authorization. The user then
authorized completing the opt-in adapter. Both providers now share typed evidence,
fixed destinations, bounded export, fresh consent checks and the same deterministic
repair/recapture gate. Provider failure cannot degrade required review to a static
pass. [Operations](browser-ui-ux-validation.md).

## 2026-10-07: generic project work and modular GUI

Project organization is a Git-owned declaration, while operational evidence stays
in the canonical workflow store. A linked task needs one owner and one stable
identity; missing evidence must not become executable or verified. Declared
dependencies explain planning without changing runtime authority. Snapshot identity
includes declaration changes so confirmations cannot retain stale context.

The Angular GUI now separates core services, shared presentation and lazy feature
routes. Signals hold view state; RxJS cancels superseded reads and manages polling.
Native dialog behavior supports the mobile drawer and action confirmation without
Bootstrap JavaScript. Actual browser CSS checks remain necessary under strict CSP.
Recorded-fact Q&A provides useful local citations without implicitly exporting source
to providers. [Frontend guide](../ui/control-center/README.md),
[project declarations](project-work.md) and [operations](control-center.md).

## 2026-10-07: embedded read-only diff scope

The user selected an embedded read-only viewer while leaving full review workflow
outside the GUI. Exact historical base content must come from the recorded Git
object, not the current working file; Git checkout conversion and final newlines
also need explicit presentation. File reads bind to a server-selected index and
exact artifact, validate proposed-byte hashes and reject unsupported/oversized
content without partial diffs. Basic code colouring uses inert text spans.
Viewing code is an inspection action, separate from human source approval.

## 2026-10-08: technical standards over shared evidence

Reusable control-plane implementations need explicit evidence semantics when
adapted. Coverage inventory/applicability logic is useful, but populating
evaluated IDs cannot prove a review occurred. G1 produces actual deterministic
outcomes, reconciles immutable command execution and records pending manual checks.
An imported safe-autofix flag grants no mutation authority. Read-only reporting can
reuse the shared staging/base/policy checks while leaving lifecycle and source
approval untouched. Source and effective profile provenance remain separate.
Only reusable technical concepts are embedded in the agent. External reference
project identity and business-specific details are excluded from runtime profiles,
prompts and shared knowledge. See [the implementation scope](standards-review.md).

## 2026-10-09: end-user migration acceptance boundaries

Separate project initialization must validate every root pair before governance
writes. An external session record is useful provenance but does not automatically
configure later commands or create an executable target foundation. Accepted ADRs
must reach the planner, including when exports live outside the source. Provider
context must distinguish architecture precedence from execution authority.

Platform health and migration readiness are different claims: restricted execution
and missing browser coverage must appear as prerequisites even when doctor passes.
The current model setting must be recognized alongside its compatibility alias.
Live provider disclosure and human-only execution/ChangeSet approvals remain
separate boundaries. See [acceptance hardening](end-user-acceptance-hardening.md).

Repeated basenames are not entity identities. Pod components and their templates
need stable path-qualified graph IDs; aggregation must reject conflicting IDs
instead of silently retaining the last node. Diagram identifiers also need to
preserve distinctions lost by punctuation replacement. Neither lossless identity
nor an empty edge set certifies complete semantic dependency discovery.

## Signed role authority and Git membership — 2026-10-09

Capability settings are ceilings, not membership. Resolve current stable OS
identity through signed project roles, and bind durable operations and approvals
to that principal and access revision. Recheck at worker/file boundaries and before
replaying receipts. A session token and an actor display label cannot prove owner
authority. New keys and incoming owners require possession/consent proofs.

Bind directory imports to an owner-approved provider repository ID; otherwise a
request can substitute a different repository's users. Keep Git roles informative
and require explicit agent roles. Normalize governance JSON/line endings before
hashing to avoid Windows checkout noise without accepting ambiguous duplicate keys.

Active policy reads should use an externally pinned verified manifest rather than
replaying unbounded history under writer locks. Keep access activation independent
of long validation leases, with access-before-apply ordering. Raw Git enforcement
requires a trusted remote gate outside candidate code. [Implementation](rbac-and-users.md).
