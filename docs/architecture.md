# Architecture

## Current boundary

Phases 0 and 1 contain configuration, typed domain models, a CLI health check, and
deterministic repository inventory. The package uses a `src` layout so tests exercise the
installed package rather than importing directly from the checkout by accident.

```text
CLI/composition root
    -> InventoryService
        -> FilesystemInspectorPort <- SafeFilesystemInspector
        -> FrameworkAdapterRegistry <- EmberClassicAdapter / AngularAdapter
    -> InventoryReportWriter
    -> domain models
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
`MIGRATION_AGENT_MODEL` is optional because Phase 0 performs no model call. Configuration
does not read or expose an API key.

## Agent runtime boundary

Phase 2 introduces the provider-neutral `AgentRuntimePort` application boundary:

```text
CLI/composition root
    -> AnalysisService
        -> InventoryService
            -> FilesystemInspectorPort <- SafeFilesystemInspector
            -> FrameworkAdapterRegistry <- EmberClassicAdapter / AngularAdapter
        -> SnapshotFileReader
        -> AgentRuntimePort <- GeminiRuntimeAdapter (DEFAULT)
                            <- OpenAIAgentsRuntimeAdapter (PARALLEL)
                            <- FakeAgentRuntime (OFFLINE)
    -> AnalysisReportWriter
    -> domain models (AnalysisResult, AnalysisFinding, EvidenceReference)
```

The core domain and application layers remain strictly provider-neutral. Neither `google.genai`
nor `agents`/`openai` types cross into the domain or application services. Google Gemini is the
default configured provider via the official Google GenAI SDK; OpenAI is supported as a parallel
provider via the OpenAI Agents SDK; `FakeAgentRuntime` enables 100% offline verification. Remote
Agents SDK trace export is disabled by default.

The agent interacts with the repository exclusively through bounded read-only tools:
`query_inventory` (accessing pre-built inventory data) and `read_repository_file` (accessing eligible
snapshot files with character and line boundaries). Post-generation evidence validation cross-references
all cited evidence paths against the deterministic inventory, marking any unverified references and
downgrading finding confidence.

The source repository remains strictly read-only. Report outputs must reside in a separate non-overlapping
root and are written atomically. Later phases will introduce staging workspaces, Git governance, and
plan lifecycle management. Implementations and tests remain fully portable across Windows and Linux.
