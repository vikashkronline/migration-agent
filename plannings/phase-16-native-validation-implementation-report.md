# Phase 16 native validation implementation report

Date: 2026-10-05. Scope: the user-authorized native validation amendment, with the
existing Phase 16 CLI/MCP/shared apply workflow preserved. No GUI phase started.

## Delivered

1. Typed restricted/native/container selection at the trusted launcher. Explicit
   native ignores leftover image configuration and does not discover Docker/WSL.
   Unconfigured launchers stay restricted; configured images retain container
   compatibility. Project execution/network/filesystem/assurance policy prevails.
2. Human-only `agent validation authorize`, `revoke`, `status`, and saved-step
   `repair`. Authorization displays the diff, exact profiles, local-account trust
   warning, identities and bounded repair scope; interactive digest confirmation
   is required. No MCP authorization or backend-selection endpoint was added.
3. External transactional consent records bind clean project/base, plan/step,
   policy, catalog profiles, toolchain/supporting modules, offline dependencies,
   scope, repair budget, actor/assurance and at most one-hour expiry. Revocation
   works while validation holds its writer lease. Mode A checks active external
   Ed25519 authority; Mode B retains its documented same-account limitations.
4. Direct absolute Node/JavaScript entry-point execution for fixed lint/typecheck/
   test/build templates. Repository executable impersonation and unsafe links
   fail closed. Dependencies are operator-provisioned, copied to staging and
   fingerprinted; validation does not install/download packages or run install
   lifecycle scripts. Optional verified Chrome/Chromium identity is supported.
5. Positive child environments with fresh external home/temp/cache directories,
   no inherited provider/SSH/startup environment, bounded/redacted streaming output,
   60-second command deadline and existing lease/cancellation heartbeats.
6. Atomic Windows Job Object assignment with kill-on-close, no breakaway, process/
   memory/CPU limits and checked descendant cleanup. A separate Linux guardian
   observes parent pipe closure and reaps/kills its process group; unsupported
   hard guarantees reject execution. Linux runtime acceptance remains unmeasured.
7. Version 2 immutable backend provenance shared by CLI/MCP validation, review and
   apply. Backend/policy, consent/trust, toolchain/dependency/input identities and
   cleanup are checked again before source approval/apply. Fake/report/legacy
   evidence cannot authorize apply. Revalidation invalidates prior approval without
   adding lifecycle states or rewriting historical hashes.
8. Repairs keep distinct ChangeSets, staging, validation and separate exact apply
   approval. Saved-step resume avoids creating a different plan after the human
   grants native consent. Existing locks, leases, backups/recovery, durable request
   semantics and container controls remain shared.
9. Setup previews include non-secret backend/toolchain settings; doctor reports
   mode and missing native prerequisites without executing repository code. Status
   includes execution backend and consent identity. Operator/host instruction packs
   and the required documentation surfaces are updated.

## Findings resolved during implementation

- Legacy live validation/run/resume could execute outside the shared consent gate
  even though their reports could not authorize source apply. Those report paths
  now accept fake execution only; live callers use saved staged plan/step commands.
  Restricted/native/container configurations are tested against these bypasses.

- The existing execution record had no backend/trust provenance. New apply now
  requires version 2 evidence through the composed execution gate. Test harness
  approval fixtures explicitly inject a test gate; ordinary fake runners remain
  unsupported in production.
- Revalidation previously accepted only staged/failed states. The existing twelve
  states now permit revalidation from passed/review/approved checkpoints, clearing
  the old approval and requiring a fresh exact digest review.
- Fresh Windows environments initially caused the real installed npm CLI to fail
  with `ERR_INVALID_ARG_TYPE` for its nested script launch. Native consent now
  binds the verified system command processor and the child gets an explicit
  `ComSpec`/npm script-shell path. Top-level execution remains direct Node argv.
- A standalone run could stop for consent but lacked a saved-step repair resume
  path. `agent validation repair` resumes shared validation/repair, optionally with
  configured provider diagnostic guidance; it cannot authorize execution/apply.
- Container evidence now binds its resolved Docker executable identity and pinned
  image. The runner receives that exact verified engine, and image/engine drift
  invalidates evidence. Container environment/CPU/output policy describes its
  actual controls separately from native controls.
- Windows parent crash, normal exit and heartbeat cancellation need tree cleanup,
  including descendants that outlive the first process. Atomic jobs and checked
  cleanup replace reliance on top-level process exit for native execution.

## Verification

Focused offline Windows evidence before the combined gates:

- 26 new native cases passed before the real npm issue was found; that issue was
  reproduced both with and without a job and corrected.
- Eight focused cases then passed, covering real installed npm, bounded/redacted
  output, input mutation, consent revocation, timeout/cancel/lease/revoke cleanup.
- Seven additional cases passed: real Node repair/restaging/apply with separate
  human fixtures, provenance tampering, human CLI consent/revocation, and atomic
  assignment failure preventing code launch.
- Windows child/grandchild cleanup and dedicated supervisor-crash tests executed
  against actual processes. Synthetic credentials and disposable source repositories
  were used; no provider key/network is required.
- Eleven focused regressions passed after the combined run exposed an outdated CLI
  test fixture: the fixture now injects its explicit execution gate when reopening
  the runtime. This preserves the production rejection of fake evidence. The same
  focused run verified consent renewal and all nine legacy-entry-point bypass cases.
- Linux-targeted static checking passed for all 108 source files. This confirms type
  portability; it does not establish Linux process-supervision acceptance.

All combined repository gates passed on 2026-10-05. The final full run collected
493 tests, including the 47 native validation cases. The earlier full run exposed
one CLI fixture mismatch (480 passed, two skipped); after correcting that fixture
and adding the renewal/legacy regressions, the final complete suite passed.

| Gate | Current evidence |
|---|---|
| `uv sync --all-groups` | Passed: 69 resolved, 68 checked |
| `uv run pytest` | Passed: **491 passed, 2 skipped in 807.08s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed: 227 files |
| `uv run mypy src` | Passed: 108 source files |
| `uv run migration-agent doctor` | Passed: exit 0, status `ok`, Python 3.12.14 |
| `uv run agent doctor` | Passed: exit 0, status `ok` |

Additional checks: `uv run mypy src --platform linux` passed for 108 source files;
`git diff --check` passed. Doctor ran in the default restricted mode without
repository execution, configured provider credentials, or Docker discovery.

## Acceptance and limits

Implementation fixtures are not live IDE/operator acceptance. Antigravity,
Codex, real human console/SSH signing, live configured provider, real Angular
toolchain/project acceptance, real Docker and Linux journeys remain separate
measured checks in `docs/phase-16-smoke-checklists.md`. This report does not mark
Phase 16 fully accepted.

Native execution has the permissions of the local account. Staging, offline flags,
fresh environments and jobs do not impose filesystem or network confinement.
Windows supervision covers job descendants, not arbitrary account-accessible OS
services; Linux group supervision differs and trusted code can escape its group.
Strict isolation policies must use containers or fail closed. No source rollback
is attempted for unrelated human/source drift during validation.

Provision an external Node toolchain and offline dependencies containing regular
files without credentials/unsafe links. Configure normal outputs under staging
`.angular`, `coverage`, or `dist`; proposed/tracked input overlap rejects execution.
Other output or input mutations fail validation. Approval/consent expiry and trust
changes require renewed human action; neither is silently refreshed by a model.

See [operator guide](../docs/native-validation.md) for exact setup and commands.
