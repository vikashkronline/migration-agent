# Phase 16 amendment: native validation before acceptance

Date: 2026-10-05.
Status: implementation delivered and combined quality gates passed; live acceptance pending.
Authority: the user requested adding native validation to Phase 16 before acceptance.

This amendment extends the final Phase 16 implementation plan. It makes a complete
trusted Windows migration workflow possible without Docker, WSL, or Linux, while
retaining the same validation provenance and exact ChangeSet apply gates. It is
consistent with master-plan ADR-1 and invariants 6, 7, 19, 24–29, 34, 38, and 39.
It does not implement the GUI or begin another phase.

## 1. Product contract

| Validation mode | Intended use | Execution permission | Can authorize apply? |
|---|---|---|---|
| `restricted` | Untrusted or unconfigured repositories | No repository code execution; inspection and static reports only | No |
| `native` | Explicitly trusted local projects | Operator-authorized fixed commands on the host, with tracked processes and bounded execution | Yes, after real checks pass and separate exact ChangeSet approval |
| `container` | Projects requiring stronger execution isolation | Fixed commands in the configured pinned local image | Yes, after real checks pass and separate exact ChangeSet approval |

Docker becomes optional for the trusted native workflow. A policy requiring
container isolation still requires Docker. Installing Docker never implicitly
authorizes a repository or selects a different execution mode.

Execution modes are independent of identity assurance tiers Mode A/B/C. Selecting
native execution never lowers the assurance required for execution or source apply.

Native execution is controlled host execution, not an OS filesystem or network
sandbox. A staging directory, a clean environment, and a Windows Job Object do
not prevent code from exercising other permissions of the executing OS account.
The operator must explicitly trust the execution scope, including generated code
and authorized repairs. Untrusted projects remain restricted or use the approved
container backend. Strict controls the native backend cannot enforce must cause
`EXECUTION_POLICY_UNSUPPORTED`, never a claim of successful isolation.

## 2. Mode selection and compatibility

- Introduce a typed `ValidationMode` at the trusted launcher/settings boundary.
  Proposed setting: `AGENT_VALIDATION_MODE=restricted|native|container`.
- Explicit operator configuration selects the mode. MCP/model arguments cannot
  select a backend, downgrade policy, or enable native execution.
- With no explicit mode, retain `container` for installations already explicitly
  configured with `AGENT_VALIDATION_IMAGE`; otherwise use `restricted`.
- Container mode retains the pinned-image and cleanup requirements. Missing Docker
  or an invalid image produces the existing isolation error, without native fallback.
- Selecting `native` does not require or probe Docker or WSL. A leftover image
  setting does not override an explicitly selected native mode.
- Platform/project policy precedence remains authoritative. Configuration cannot
  override a policy requiring containers, denied execution, stronger assurance,
  or enforceable network restrictions. Protected policy changes require the
  existing authorized authority procedure, not a model-supplied switch.
- CLI and MCP use the same selector and policy evaluation. `doctor`, setup preview,
  and status show the effective mode and missing prerequisites without executing
  repository code or revealing environment contents.

## 3. Operator consent for risky native execution

Native code execution permission is distinct from source-change approval. A model
cannot grant it by passing `trusted=true`, an actor string, an approval token,
`--auto-approve`, or a fake validation result.

Use a small typed `NativeExecutionConsent` in external operational storage and the
existing trusted human console boundary. Proposed human commands are
`agent validation authorize` and `agent validation revoke`; these are now implemented.
Expose status/request instructions through existing tools,
without adding a model-callable authorize/signing endpoint.

Consent must bind canonical project identity, clean source revision/fingerprint,
plan/step, effective execution-policy digest, permitted fixed command templates,
toolchain/dependency identity, approved file scope, repair budget, actor/assurance,
creation/expiry, and revocation identity. Use a bounded lifetime, initially at most
one hour. Minimum assurance is the policy requirement and never below Mode B.
Mode B retains the existing same-account trust limitations; Mode A must be honored
where policy requires it. No private keys or reusable bearer secrets are persisted.

The human review must explain that local code runs with the account's permissions,
show the staged scope and exact templates, and disclose whether the requested
bounded repairs are included. A consent may cover the reviewed step and its
explicitly approved in-scope repair budget, avoiding a new execution prompt for
each iteration. It must not cover changes to scripts, dependencies, executable
identity, validation configuration, policy, or expanded scope. Such changes,
source drift, expiry, or revocation require renewed consent.

Check consent before launch and on every existing lease/cancellation heartbeat.
Revocation stops outstanding native validation and prevents future launches.
Expiry/revocation does not resume an interrupted process. Already completed
evidence remains historical; new execution and new apply authorization require
the active effective policy to accept that evidence. An approval already recorded
must not silently survive a relevant policy/trust-context change.

## 4. Native adapter and toolchain handling

Keep domain/application services independent of subprocesses and OS APIs. Reuse
the existing `FencedValidationPort` and shared `ApplyService`; implement native
execution and platform-specific process management in adapters. A small selector
chooses the backend. Do not introduce a second apply workflow or generic shell API.
Share bounded output, diagnostics, cancellation, and lease handling where useful;
the test-only `permitted` escape hatch must not become a production setting.

1. Resolve installed executables to absolute canonical paths outside source and
   staging. Reject PATH/current-directory impersonation, unsafe links, and changed
   executable/entry-point identities before launch.
2. Execute fixed, typed templates for supported LINT, TYPECHECK, TEST, and BUILD
   profiles. No raw model shell text, arbitrary flags, executable paths, or inline
   shell bodies are accepted. Top-level adapter launches use argument arrays and
   `shell=False`.
3. Handle Windows npm/TypeScript/Angular `.cmd` launchers explicitly: resolve
   trusted `node.exe` and verified CLI JavaScript entry points and launch them
   directly. Do not repair `.cmd` failures by enabling arbitrary shell execution.
   npm scripts can invoke shells internally; their code is covered by the explicit
   native trust decision and is not made safe by the executable allowlist alone.
4. Use a positive environment allowlist. Set fresh external HOME/USERPROFILE,
   temporary, and cache locations where tools require them; exclude provider keys,
   SSH agent sockets, user credential configuration, startup hooks, and inherited
   application environment. Redact bounded diagnostics before persistence/display.
   This does not prevent trusted code from independently accessing account data.
5. Do not elevate privileges, launch visible helper windows, provision OS services,
   modify firewall rules, or execute against the authoritative source directory.
   Native preflight reports incompatible/elevated execution contexts and fails
   closed where the approved policy cannot be honored.
6. Define toolchain and dependency provisioning explicitly. Reuse approved local
   dependencies or an operator-prepared offline cache; verify the toolchain/entry
   points and dependency manifest identity. No implicit `npm install`, downloads,
   install lifecycle scripts, or network fallback in validation/MCP. Missing
   dependencies produce actionable diagnostics and no passing provenance.
7. Support ordinary native build/test output in approved staging-only directories,
   such as configured build, coverage, and cache locations. Identify them before
   execution; reject overlap with source/state/trust and with proposed input files.
   Fingerprint all validation inputs before/after; writable output exclusions are
   explicit, cannot hide input changes, and are part of the execution policy.

Network requirements must be truthful. Offline package-manager flags are not OS
egress enforcement. If policy requires denial or an egress allowlist the native
adapter cannot enforce, reject execution or require separately verified host
controls. Trusted native access must follow the explicitly authorized host network
policy; no backend may label unrestricted access as network-isolated.

## 5. Process lifecycle and fencing

- Preserve the existing limits of at most 60 seconds per command, 64 KiB retained
  output, bounded worker count, redacted output, and periodic lease/cancel checks.
- On supported Windows, put the process in a Job Object at creation, with kill on
  last handle close and no permitted breakaway. Prefer atomic assignment through
  `PROC_THREAD_ATTRIBUTE_JOB_LIST` to avoid the crash window between creating a
  suspended process and assigning it. Verify nested-job compatibility and fail
  before repository code runs if supervision cannot be established.
- Apply supported process-count/memory/CPU limits through the Windows adapter;
  retain actual effective limits in provenance. A requested unsupported hard limit
  cannot silently disappear.
- Timeout, cancellation, consent revocation, lease loss, normal completion, and
  server death must leave no supervised validation descendants or held output
  handles. Cleanup uncertainty blocks PASSED provenance.
- On Linux, use a separate OS adapter with explicit process-group/session cleanup
  and tested crash supervision. Do not claim identical kernel guarantees. Reject
  policies requiring unsupported guarantees. Linux verification is a separate
  portability gate, not a prerequisite for the Windows native journey.
- Recheck source base and staged inputs after validation. Drift invalidates
  provenance and source apply. Do not silently revert unrelated human/source
  changes. This is detection, not proof that native code was filesystem-confined.

## 6. Immutable provenance and shared apply eligibility

Extend/version `ValidationExecution` to bind backend, effective execution-policy
digest, native consent identity when applicable, fixed template catalog version,
resolved toolchain/entry-point and dependency identities, effective environment
policy and limits, and input/staging fingerprints, alongside existing results and
ChangeSet/project/plan/step identities. Persist deterministically without raw
environment values or secrets.

Both real native and real container executions may supply PASSED evidence when
the effective policy permits their recorded backend and all required profiles
pass. Restricted/static reports, fake/test runners, unverified cleanup, or
unsupported controls cannot do so. Existing approval continues to bind the
immutable validation digest; exact human ChangeSet review remains mandatory.

Backend/policy/toolchain/dependency/input changes require new validation and new
approval. Repaired bytes still require a distinct ChangeSet, restaging, validation,
and fresh apply approval. Keep all twelve lifecycle states, durable request
semantics, OS apply locks, lease fencing, backups, and recovery behavior.

Define compatibility for stored records explicitly: legacy evidence lacking backend
provenance is marked unsupported for new apply authorization and must be revalidated.
Do not infer trusted native evidence from an old report, rewrite historical hashes,
or silently reinterpret existing approvals. Document the revalidation path and
preserve old records as history.

## 7. Ordered implementation packages

1. **Contracts and policy:** typed modes/consent/provenance, precedence, trust and
   policy checks, record-version compatibility, and focused contract tests.
2. **Native Windows execution:** verified toolchain launch, environment/workspace
   handling, output bounds, Job Object supervision, cleanup and focused offline tests.
3. **Shared workflow wiring:** backend selection for CLI/MCP, execution consent and
   revocation, immutable execution persistence, approval/apply gates, repair loops.
4. **Linux compatibility and container regression:** OS-specific adapter boundaries,
   no import-time Windows-only dependencies, container behavior preserved, no fallback.
5. **Setup and docs:** backend selection in setup/config preview without granting
   consent; doctor/status diagnostics; host instructions and operator guide.
6. **Combined gates and acceptance:** required repository commands, then measured
   Windows journeys in Antigravity, Codex, and standalone CLI without Docker/WSL.

Implementation is now authorized and tracked in
`phase-16-native-validation-implementation-report.md`. Repository gates passed
with 491 tests passed and two skipped. Complete separate live operator/host
acceptance before closing Phase 16. Do not begin GUI work.

## 8. Required regression and acceptance tests

- Unconfigured/untrusted repositories do not launch code; selecting native alone
  cannot mint consent. Mode C, forged consent, expired/revoked consent, policy
  conflicts, changed toolchains, and expanded repair scope fail before execution.
- Missing Docker in container mode never switches to native. Explicit authorized
  native mode works when Docker/WSL are absent and Docker discovery is unavailable.
- Windows paths with spaces/Unicode and real installed Node CLI entry points work
  without direct `.cmd` execution or a model-controlled shell. Repository-provided
  `node`, `npm`, `tsc`, `ng`, and `pytest` impersonation is rejected.
- Supported profiles actually execute offline fixture commands. Build/cache outputs
  stay in declared staging locations; input changes and source drift block approval.
  Strict unsupported network/filesystem controls fail closed with useful diagnostics.
- Synthetic environment credentials/startup hooks do not reach the child; output
  is bounded during streaming and recognized credentials are redacted. Tests use
  synthetic data and require no provider API key or network.
- Child/grandchild cleanup is measured on Windows for timeout, cancel, lease loss,
  revocation, normal exit, parent crash, and launch/assignment failure. Kill the
  disposable supervisor in a dedicated integration test; verify no orphan process.
- Native and container results cannot be relabeled or mixed across artifacts.
  Backend/policy/toolchain/dependency tampering, incomplete profiles, fake results,
  legacy evidence, and repaired-byte reuse reject apply authorization.
- Positive native validation → separate real human review → apply succeeds once
  against a disposable Windows Git fixture. Approval leaves source clean; backups,
  rollback, replay, and recovery retain their current guarantees.
- Repeat the complete native journey in Antigravity, Codex, and configured standalone
  CLI without Docker/WSL. Include failed validation and an in-scope repair covered
  by consent, then fresh exact apply approval. Record actual versions and outcomes.
- Run the unchanged container regression suite and record a real container journey
  for the optional container backend. Its acceptance evidence remains separate.
- Run all six repository gates and `uv run agent doctor`; update the eight required
  documentation surfaces and phase status with actual results. Run Linux gates
  separately and record exactly which native guarantees were verified there.

## 9. References and evidence boundary

Microsoft documents process grouping, limits, termination and kill-on-close for
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
Its guidance on [creating a process directly in a job](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812/)
describes the atomic-assignment approach and the suspended-process orphan window.
[Node's Windows process documentation](https://nodejs.org/api/child_process.html#spawning-bat-and-cmd-files-on-windows)
describes the `.cmd`/`.bat` launcher limitation. These are design inputs;
implementation tests are recorded in the implementation report, and live IDE
acceptance needs its own measured evidence.
