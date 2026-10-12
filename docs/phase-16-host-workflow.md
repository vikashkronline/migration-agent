# Phase 16 host workflow

Implementation log started 2026-10-04. This document records the 16B–16D work separately from measured IDE acceptance. SDK clients are automated fixtures, not Antigravity or Codex observations.

The [current workflow](migration-workflow.md) supersedes historical in-place apply
descriptions for external-governance migrations. New artifacts bind a separate
cumulative target and owner-signed architecture. Declared implementation steps
can use bounded initial generation proposals as well as deterministic adapters.

## 16B: proposals and durable state

Host reasoning uses the IDE's model session. The server does not create a model runtime or require a provider key for evidence reads or proposal submission.

- `migration_evidence_read` checks inventory-style content hashes, line ranges, and optional cited symbols before returning at most 32 KiB across ten excerpts.
- Analysis findings require current source citations. Plan proposals require a saved analysis against the same clean Git base, grounded step scope, a supported deterministic transformation, and a valid dependency DAG.
- The server assigns analysis, plan, run, and operation IDs. Operational records live in the configured state directory. Reading a missing policy returns defaults without initializing `.agent` in the source.
- A project/request pair binds the operation kind and canonical payload digest. Replays return the original handle; changing the payload is a conflict. Terminal results have seven-day retention; request tombstones prevent expired requests from executing again.
- Workflow records enforce exactly twelve named states and compare-and-swap versions. Base drift clears downstream artifact references and cannot resume directly into staging. A new inspected plan is required.
- SQLite writer leases use an increasing generation and expiry, verified inside state transactions. A portable nonblocking OS file lock provides the separate apply critical section boundary.
- Interrupted validation fails and requires another validation. Interrupted repair requires a fresh inspected plan. Interrupted apply is classified against target/backup metadata; target completion is recorded, and base or ambiguous results require explicit recovery.

The reference plan mentions `APPLY_FAILED` in one recovery example but excludes it from its twelve-state table. The implementation preserves the table and uses `RECOVERY_REQUIRED` with a `base` classification for an interrupted apply whose original bytes are intact. It does not silently reuse the approval.

Operation status reports bounded Git working tree cleanliness/dirty paths, step lifecycle, transferability, artifact IDs, validation provenance, and a digest identifying recorded failure diagnostics. Repairs must cite that diagnostic digest and stay within the previous ChangeSet's file scope.

## 16C: shared guarded workflow

CLI and MCP use the same application services for staging, validation, review,
approval, and apply. Legacy plan approval, fake validation, skipped checks, and
dirty-base overrides cannot authorize source writes. Plan digests are retained in
workflow records; validation is an immutable execution record bound to the exact
ChangeSet, stage fingerprint, results, and required plan profiles.

Human review displays the full bounded diff and requires an exact digest
confirmation in an interactive terminal. Mode B trusts the local operator and
external state directory; it does not protect against arbitrary processes running
under that same OS account. Mode A verifies an active external Ed25519 authority
bound to the Git root commit and uses an SSH signer without reading private key
bytes. An unconstrained shared signer is not proof of human intent.

Approvals expire after fifteen minutes, carry a single-use nonce, and bind all
source, policy, validation, actor, and artifact identities. Renewed review clears
the old approval reference. Repairs always create a new artifact and clear stage,
validation, and approval references. Approval records and backups stay outside
source throughout review and apply.

The apply OS lock is global to the canonical target identity (historical in-place
records retain their project identity), independent of the
configured state directory. Its critical section covers preconditions, backups,
approval consumption, durable write intent, mutations, rollback, and postconditions.
Every mutation checks the OS lock and renewed SQLite lease generation. Failed
rollback or uncertain interruption enters `RECOVERY_REQUIRED`. Explicit
`agent recover` verifies a completed target or a fully restored clean base; it
does not replay source writes. A restored base requires a fresh plan.

Container validation uses fixed commands in a locally installed image pinned by digest, with
network disabled, read-only root/staging mounts, a non-root user, restricted
capabilities, and resource limits. Git and Docker resolve to absolute installed
executables outside source; Docker also cannot reside under staging. Output and
runtime are bounded; cancellation checks the lease and stops the child/container.
Unverified container cleanup blocks successful validation provenance. Missing
isolation or unsupported toolchain/writable output requirements fail closed.

The standalone live pipeline uses its configured provider for analysis/planning.
Its bounded repair loop tries deterministic strategies first, then typed provider
diagnostic guidance where available. Recognized strategies generate candidate
bytes in memory; they enter the same typed repair submission, restaging, and
validation gates used by the host. Unsupported guidance, repeated failures, and
budget exhaustion stop the loop. The provider cannot supply shell commands or
approval. `agent submit-repair` also accepts a bounded external proposal file.

## 16D: client setup and instruction packs

`agent mcp setup` previews a named stdio entry by default. Explicit `--write`
performs guarded configuration updates with backup, conflict checks, and atomic
replacement. JSON preserves unrelated entries; TOML preserves existing content
and refuses replacement of a different existing server entry. Installation
interpreter paths and argument arrays support paths with spaces and independent
client working directories.

The packaged skill and Codex instruction pack explain evidence grounding,
operation polling/replay, repair, human review, apply, and conservative handoff.
They are workflow guidance; application services enforce the security gates.
See `phase-16-client-setup.md` for setup, trust, validation provisioning, and recovery.

CLI/MCP startup loads model SDKs only when the standalone provider is selected.
Ordinary host workflows and diagnostics do not initialize either provider SDK.

## Verification scope

Focused tests cover replay conflicts, cross-project reads, grounded proposals, cycles/symbols, drift invalidation, stale lease generations, checkpoint versions, cross-process OS lock exclusion, cancellation, and all three interrupted-apply classifications. Per-milestone repository gate results are recorded in `docs/phase-status.md`.

Actual primary-host smoke sessions and a human-only signing channel are separate acceptance evidence. No full GUI is part of this phase.

## Native validation amendment

The trusted launcher selects restricted/native/container independently of identity
assurance. `NativeExecutionConsent` is a separately signed, expiring, revocable
human execution decision. It binds the clean base, fixed profiles, full execution
policy, installed toolchain/dependencies, reviewed step scope and repair budget.
No MCP authorization or backend-selection tool is added.

`ValidationBackend` implements the existing fenced validation port and a typed
execution gate. `ApplyService` persists version 2 immutable provenance and checks
the active backend/policy/trust/toolchain again during review and apply. Ungated
test/report runners produce unsupported historical evidence. Revalidation uses
the existing twelve states and invalidates prior approval; repair still creates
new ChangeSets. Legacy records are not rewritten or promoted.

Windows supervision uses atomic Job Object assignment, positive fresh environments,
fixed Node entry points, offline staged dependencies, streaming output bounds and
verified cleanup. Linux uses a separate guardian/group adapter. Native execution
is trusted account execution and cannot satisfy kernel filesystem/network isolation.
See [operations and precise limits](native-validation.md).
