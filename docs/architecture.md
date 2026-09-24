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
