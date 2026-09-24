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


