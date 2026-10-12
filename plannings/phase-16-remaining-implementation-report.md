# Phase 16 remaining implementation and review report

Date: 2026-10-04. Scope: the authorized remaining Phase 16 work following the
Gemini implementation review. The master plan and final Gemini implementation
plan were consulted. Existing changes were preserved. No later GUI phase was
implemented, and no live client configuration or source migration was installed
in the operator's projects.

## Implementation disposition

| Area | Implementation and correction |
|---|---|
| 16A review | R01–R09 and R11 remediated; R10 compatibility claims corrected. Actual IDE measurements remain pending. |
| Grounded host reasoning | Typed evidence, analysis, plan, and repair proposals; current citations, supported scope, DAG checks, protected paths, and bounded content. Host reasoning needs no separate server model key. |
| Durable operations | Project/request payload binding, replay handles, expiry tombstones, status/cancellation, twelve states, source drift invalidation, generation leases, and crash reconciliation. |
| Shared source apply | CLI/MCP share exact artifact, clean-base, plan/policy, immutable validation, human approval, lock, backup, write-intent, rollback, and postcondition checks. Legacy bypass paths fail closed. |
| Human approval | Full diff/digest review, interactive exact confirmation, external approval storage, expiry/single-use nonce, genuine Ed25519 authority verification, and external Git-root-bound trust. No model-callable approve/signer/token endpoint. |
| Validation isolation | Fixed commands, sanitized environment, pinned local container, no network/pulls, read-only mounts, non-root/resource restrictions, bounded output/time, lease/cancellation checks, and verified cleanup before success. |
| Executable resolution | Repository Git/Docker impersonation rejected; absolute installed executables used. Windows process termination resolves the system executable directly. |
| Standalone parity | Configured provider analysis/planning; bounded deterministic/provider-guided repair through the typed host repair gate; restaging/revalidation/new approval; external proposal CLI; identical guarded apply. |
| Setup | Preview-first Codex/Antigravity stdio configuration, secondary JSON client support, backups/atomic writes/conflict checks, preserved unrelated settings, paths with spaces, and stable installation interpreter. |
| Host packaging | Migration skill and Codex instructions; evidence, repair, handoff, human review, and recovery guidance. No source AGENTS.md replacement. |
| Recovery | Startup classifies interrupted apply without replay. Explicit recovery verifies completed target or restored clean base. Ambiguity remains blocked; restored base invalidates the old plan. |

## Further gaps found and corrected during implementation

1. Legacy transformation/pipeline apply could bypass exact ChangeSet review.
   Source writes now require the shared service; plan auto-approval cannot apply.
2. Mutable validation results or incomplete profile coverage could represent a
   false passing check. Approval now verifies immutable execution provenance,
   unchanged staging, and every required plan validation profile.
3. An apply lock rooted under a configurable state directory could leave two
   launchers with separate locks. The OS lock is now global to the canonical
   project identity; SQLite leases still fence each state write and source write.
4. Executable lookup could select repository-provided Git/Docker. The runtime
   rejects such executable paths before launch.
5. Container cleanup errors could otherwise preserve a passing validation result.
   Unverified cleanup now fails validation instead of creating passing provenance.
6. The initial live standalone workflow bypassed its bounded repair loop after
   validation failed. Recognized deterministic/provider diagnostic guidance now
   enters typed repair submission, a new stage, and a new validation execution.
   Repeated failures, unsupported guidance, and exhausted budgets stop safely.
7. Approval expiry and ambiguous recovery needed explicit lifecycle handling.
   Renewed review clears the prior nonce; explicit recovery never automatically
   replays writes or reuses a consumed approval.
8. SDK shutdown during asynchronous cancellation needed shielding so background
   operations and connections receive cleanup.
9. A subprocess gate exposed slow CLI startup with eager imports of both provider
   SDKs. Runtime resolution now imports only the selected provider; a subprocess
   contract verifies ordinary CLI startup does not load either model SDK.

## Verification

All required repository gates passed on Windows with Python 3.12.14:

| Command | Result |
|---|---|
| `uv sync --all-groups` | Resolved 69 packages; checked 68 |
| `uv run pytest` | **444 passed, 2 skipped in 677.80s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | 219 files already formatted |
| `uv run mypy src` | 104 source files; no issues |
| `uv run migration-agent doctor` | Exit 0; status `ok` |
| `uv run agent doctor` | Exit 0; status `ok` |

The final pytest invocation used `-o addopts=''` for full progress output rather
than configured quiet output; the complete suite collected 446 tests. Seven
focused standalone repair and CLI startup regressions passed before this run.
Earlier separately recorded gates were 402 passed/2 skipped for 16A remediation
and 414 passed/2 skipped for 16B; the combined result above supersedes them for
the current implementation. Neither fixture count establishes real IDE acceptance.

The skill passed the official `skill-creator` quick validator using a temporary
PyYAML environment; PyYAML was not added to application dependencies. Tests use
disposable repositories, synthetic diagnostics, human review fixtures, and
ephemeral signing keys. They require no network or provider API key.

## Remaining acceptance and practical limits

**Phase 16 must not yet be declared fully accepted.** The implemented interfaces
and automated SDK tests do not establish real client interoperability or human
intent. Execute the dated checklists in `docs/phase-16-smoke-checklists.md`.

| Remaining evidence | Required action |
|---|---|
| Antigravity and Codex | In each installed client, exercise the fifteen-tool journey, repair/replay/cancellation/recovery, and exact artifact human approval/apply against a disposable fixture; retain sanitized versions/results. |
| Human review/signer | An operator must exercise actual interactive CLI review and signing. Native human-only IDE hooks are unverified and are not implemented or claimed. Terminal-assisted review remains the supported fallback. |
| Real container runtime | Provision the trusted digest-pinned toolchain/dependencies and verify successful compilation/tests, resource restrictions, cancellation, and cleanup on the installed Docker engine. Fixture command assertions do not prove kernel isolation. |
| Linux | Run all six gates and process/lock/recovery checks on Linux; only Windows execution is recorded here. |
| Standalone live provider | Exercise real configured analysis/planning and actionable diagnostic-guided repair with the operator's provider outside the offline test suite. |
| Cursor/Claude | Secondary configuration generation is tested; runtime smoke acceptance remains pending. |

Mode B is a trusted local operator assertion, not cryptographic protection against
another process with arbitrary access to the same account, interactive terminal,
or state database. Mode A additionally requires an authorized external signer
under human control; a shared unconstrained SSH agent alone does not prove human
intent. The instruction pack prohibits automated console approval, but it cannot
isolate arbitrary host tools running under the same OS account.

Validation requires a locally provisioned image pinned by digest. Missing
toolchains, dependencies, isolation, or writable output configuration fail closed;
there is no automatic host subprocess fallback. Codex TOML setup refuses replacing
a different existing named entry and requires manual reconciliation. Source drift
requires a fresh plan; successful apply does not automatically commit or rebase
later steps.

Legacy apply actor/backup/project arguments remain compatibility parameters;
guarded apply uses the human record, external state backups, and positional source
binding. See the operation guide for the supported current workflow.

The next acceptance action is an operator-assisted Antigravity and Codex smoke
session using the supplied setup and checklists. Future GUI work remains a
separate phase and is unnecessary for this workflow.

## Subsequent scope change: native validation before acceptance

The user subsequently authorized adding native validation to the Phase 16 plan.
The next implementation action now precedes host acceptance: execute
`phase-16-native-validation-mode-plan.md` to support trusted Windows projects
without Docker/WSL/Linux, with explicit native execution consent and unchanged
exact artifact approval/apply checks. Container mode remains optional and no
automatic fallback is allowed. Native implementation and its new quality gates
are pending; this report's 444-passed result covers the prior implementation.
