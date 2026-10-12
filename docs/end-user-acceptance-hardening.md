# End-user acceptance hardening

The 2026-10-09 acceptance run uses a fresh external project for an existing Ember
source. Source inspection, governance recording and readiness checks use the CLI.
Target application files are never authored manually during this workflow.

## Separate initialization

```powershell
uv run migration-agent init C:/migration-session/project --id acceptance-session `
  --source C:/source-app --state-dir C:/migration-session/state `
  --staging-root C:/migration-session/staging
```

Initialization stores typed roots in `.agent/migration-session.json` under the
external project. It rejects equal, ancestor and descendant overlaps between any
two roots before creating governance. Source must be an existing directory.
Equivalent repeated initialization preserves the record; different roots require
a fresh project directory. Linked governance paths are rejected. Ordinary `init`
without `--source` retains its existing behavior.

The session record documents roots; subsequent commands still require explicit
state/staging flags. Inventory and analysis select the source. `plan create`
uses `--output C:/migration-session/project` to keep governance exports external.
Record ADRs with `decision record C:/migration-session/project` before planning.
Initialization does not install target dependencies, create a runnable target
foundation, select a provider, grant native execution consent or authorize apply.
The original source must remain read-only throughout this acceptance run.

## Architecture precedence

Standalone planning loads accepted ADRs from the selected governance output,
sorts them by ID, excludes proposed/rejected/superseded decisions and passes
typed decisions to both provider adapters. Context is limited to 50 decisions and
64 KiB of serialized decision bytes. Audit events record the accepted decision IDs.
The unified standalone pipeline also supplies its selected project's knowledge.

Provider instructions give accepted architecture precedence over migration defaults
and require conflicts or missing foundation prerequisites to remain explicit.
Decision text cannot authorize commands, approval or safety bypasses. This is
provider context, not a deterministic certification of semantic conformity or a
new ADR signature/approval protocol. Existing DAG, evidence, staging, validation
and approval gates remain authoritative.

## Readiness diagnostics

Doctor recognizes both `AGENT_RUNTIME_MODEL` and the legacy model setting.
`validation status` includes the same typed setup diagnostics as doctor alongside
per-step consent status. Restricted mode lists backend selection as an execution
prerequisite; missing browser plans are explicit. Native mode additionally lists
missing external toolchain/dependency directories and human execution consent.
Configuration presence does not prove installed tools or application behavior.
Doctor's `ok` means the platform runtime works, not that this migration is ready.

## Lossless discovered-node identity

Frontend discovery previously keyed nodes by basename. Pod components, templates
and same-named files across packages silently overwrote each other. Frontend IDs
now use `frontend:file:<repository-relative POSIX path>` for stable identity across
file discovery order and addition of unrelated files. Existing basename IDs in old
reports are superseded by fresh discovery; use the returned path IDs for impact
queries. Source and template files are distinct observed nodes.

Graph aggregation rejects conflicting entities sharing an ID instead of choosing
the last one. Mermaid uses deterministic digest identifiers so punctuation such
as hyphens and underscores cannot collapse separate nodes during rendering.
This preserves discovered evidence; the heuristic adapters still do not certify
complete semantic dependency extraction for every source framework or construct.

## Acceptance boundary

The fresh CLI inventory completed and the source-isolation ADR was recorded.
Real provider analysis was not executed: automatic approval review rejected the
attempt because its provider/destination had not been authorized. The run also
needs a confirmed target architecture and provisioned target validation foundation.
No functional tasks, target generation, validation consent, ChangeSet approvals
or source applies have occurred. No fake-runtime report is counted as migration
evidence. Resume real planning only with the approved provider/model; keep target
generation and all subsequent changes inside supported platform interfaces.

Verification results are recorded in [phase status](phase-status.md).
