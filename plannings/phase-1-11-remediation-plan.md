# Phase 1–11 Remediation Plan — GPT-6 Luna Handoff

**Status:** Proposed remediation work, not evidence that any item is fixed.  
**Source of truth:** `plannings/final/agent-platform-master-plan.md`, especially invariants 4–7, 14, 19–21, 24–29, 33–34, 38–40; `docs/phase-status.md` for the Phase 11 claims.  
**Scope:** Correct existing Phase 1–11 behavior and its tests and documentation. Do not implement Phase 12 features or broaden the supported migration syntax to make a benchmark pass.

## Execution instructions for Luna

1. Read `AGENTS.md`, the master plan, `docs/phase-status.md`, and the relevant source/tests before editing. Inspect `git status` and `git diff` first. Gemini is working on Phase 12 in the shared checkout; do not overwrite or stage its changes. Use an isolated worktree from the committed Phase 11 baseline, then integrate after Phase 12 changes are stable. The likely conflict files are `cli.py`, `adapters/governance.py`, `application/control_service.py`, and `adapters/control_api/server.py`.
2. Work through the packages below in dependency order. Keep each package reviewable, with focused tests for the behavior it introduces. Never use a source repository as a destructive test target; use temporary fixtures. Do not call a package complete when its acceptance checks are missing.
3. For security-sensitive changes, choose a fail-closed result when identity, policy, base state, ChangeSet content, validation evidence, or repository binding cannot be verified. Preserve the domain/application/adapters dependency direction and typed public boundaries.
4. Keep existing CLI/API entry points where safe. If a persisted schema or API payload must change, add an explicit version and migration or reject legacy records with an actionable message. Do not silently treat old plan-only approvals as ChangeSet approvals.
5. After integration, run the six required project gates and record their actual output in the remediation status. Do not copy historical gate results from `docs/phase-status.md`.

## Dependency order and release gates

| Order | Package | Review finding | Release gate |
| --- | --- | --- | --- |
| 0 | Baseline and regression tests | Unverified current state | Capture baseline without altering Phase 12 work |
| 1 | Path containment and file serving | R04, R07 | No read or recursive delete outside an approved root |
| 2 | Identity, trust, and policy | R02, R05 | No actor or policy bypass; real Mode A verification |
| 3 | ChangeSet approval and controlled apply | R01, R06 | Only the exact staged, validated, approved bytes can reach the target |
| 4 | Control API mutation wiring | R03 | API outcomes match persisted apply outcomes |
| 5 | Command execution and redaction | R08, R12 | Untrusted execution fails closed; no secret-bearing output persists |
| 6 | AngularJS migration correctness | R09 | Supported fixture behavior survives and output compiles |
| 7 | Control Center build and assets | R10 | Served Angular build works offline under CSP |
| 8 | Evaluation and documentation | R11 and status drift | Metrics measure actual behavior; claims match evidence |

Packages 1–5 are release blockers. Do not treat a passing unit suite alone as evidence that apply is safe. Package 6 is a blocker for claiming the Phase 11 migration target complete. Packages 7–8 are blockers for the Phase 10/11 claims recorded in `docs/phase-status.md`.

## Package 0 — Baseline and reproducible failing cases

**Files to inspect:** `domain/planning.py`, `domain/changeset.py`, `application/transformation.py`, `application/control_service.py`, `adapters/trust_store.py`, `adapters/workspace.py`, `adapters/control_api/server.py`, `adapters/container_runner.py`, `adapters/transforms.py`, `application/evaluation.py`, and their tests.

- Record the committed baseline, Python/uv versions, current test result, and the exact Phase 12 diff excluded from this work.
- Add minimal failing regression tests before each fix. Tests must use temporary repositories and state roots and must never require credentials, Docker, network, or `OPENAI_API_KEY`.
- Keep a traceability table in the final report: finding ID, implementation commit, regression test, quality gate, and any remaining limitation.

**Exit:** Every finding below has at least one failing pre-fix test or a documented reason why a static contract/build check is the appropriate proof.

## Package 1 — Constrain every filesystem path (R04, R07)

**Current code:** `adapters/control_api/server.py::_serve_static_asset`; `adapters/workspace.py::create_staging`, `apply_changeset`, and `cleanup_staging`; the path check in `application/transformation.py::apply`.

1. Resolve a requested static asset against the asset root; serve it only when it is a regular file beneath that root. Reject raw and encoded traversal, absolute paths, Windows drive/UNC forms, mixed separators, and symlink escapes. Do not send filesystem paths or file contents in error bodies. Keep SPA fallback only for safe route names.
2. Replace string-prefix containment checks with path-component-aware comparisons. Validate repository-relative `FileChange.path` once at the typed boundary and again at the filesystem adapter boundary. Reject empty, absolute, parent (`..`), drive-relative, duplicate, and symlinked destinations. Do not follow source symlinks during staging or fingerprinting.
3. Bind staging operations to a configured staging root and validated run ID. Change cleanup so callers cannot pass an arbitrary directory for recursive deletion. Confirm the resolved target stays beneath the configured root immediately before deletion; propagate deletion errors rather than ignoring them.
4. Keep source, staging, backup, and state roots distinct. Reject overlap in either direction before copying, backing up, deleting, or applying.

**Acceptance tests:** raw `/../` and encoded traversal cannot read a sentinel outside the static root; a sibling directory sharing the staging root prefix is rejected; `../`, absolute, drive-relative, and symlink paths cannot write or delete outside staging; cleanup refuses a source or unrelated sentinel directory; valid assets and staging still work on Windows and Linux.

## Package 2 — Real trust, identity, and capability policy (R02, R05)

**Current code:** `adapters/trust_store.py`, `domain/trust.py`, `domain/planning.py::verify_approval`, `ports/governance.py::ProjectPolicy`, `application/planning.py::approve_plan`, CLI approval, and GUI approval service.

1. Replace the purported Ed25519 HMAC with genuine Ed25519 signing and verification from a maintained cryptographic library. Store and verify public keys and fingerprints only; never store a private key in `.agent/`, logs, or the trust record. If HMAC is retained for a local mode, use a separately protected secret and never classify it as Mode A. Reject unsupported algorithms and malformed encodings.
2. Require at least one explicit repository binding signal in a trust record. On Mode A approval and final apply, resolve the current repository root-commit and/or verified origin and fail when a required signal is missing or mismatched. Key rotation and revocation must be explicit operations with audit evidence; a normal project file must not bootstrap its own authority.
3. Add a typed identity resolution boundary and a centralized policy decision boundary for privileged actions: `changeset.stage`, `changeset.apply`, validation command execution, policy/access writes, and GUI mutations. Resolve capabilities from versioned roles/principals plus active policy. Deny when identity, capability, assurance level, policy digest, or trusted authority cannot be established. Session token authentication remains separate from authorization.
4. Use the same policy evaluation in CLI and Control API application services. Ignore a client-supplied `actor` as proof of identity. Mode C stays read-only; enforce the master plan's Mode A requirement for production apply and security policy changes. A Mode B local development exception, if retained, must be an explicit policy setting that cannot weaken protected defaults.
5. Give policy records the documented ID, schema version, revision, and canonical content digest. Prevent a policy or role change from authorizing itself. Re-evaluate the active policy immediately before stage, validation, and apply.

**Acceptance tests:** a signature computed with only public trust-record data fails; a real Ed25519 signature succeeds for the exact payload and fails after one-byte mutation; revoked/unknown keys and missing/mismatched repository bindings fail; spoofed GUI actor and missing capability fail despite a valid session token; changed policy invalidates approval; legacy plan-only approval cannot authorize apply.

## Package 3 — Bind approval to staged bytes and enforce controlled apply (R01, R06)

**Current code:** `domain/changeset.py`, `domain/planning.py`, `application/transformation.py`, `application/validation.py`, `cli.py` preview/stage/apply, SQLite checkpoints, and run state.

1. Define one canonical ChangeSet identity independent of random preview IDs. Include the real Git base commit, complete relevant working-tree fingerprint, normalized paths, operations, file modes, and raw-byte SHA-256 digests. Recompute metadata and each content digest at every trust boundary. Reject duplicate/conflicting paths, missing bytes for create/modify, wrong operation preconditions, and any ChangeSet whose `plan_id`, step, source root, or base state differs from the selected plan/run.
2. Split plan acceptance from mutation approval. Persist a typed human approval that binds **ChangeSet digest + plan digest + active policy digest + actor identity/assurance + timestamp**. Update CLI/API review views so the exact diff and digest are shown before approval. Repaired or regenerated ChangeSets require fresh approval; no automatic reuse of a plan approval.
3. Record staging path and a manifest of staged output digests in SQLite. Record required validation profile results against the same ChangeSet digest and staged manifest. An explicit approved policy may waive a profile; record the waiver. `apply` must require this evidence and must not call `preview` as a shortcut to a new unvalidated ChangeSet.
4. Immediately before target mutation, verify: approval signature and capability; active policy; Git commit and full fingerprint; ChangeSet digest and bytes; staged manifest correspondence; passing required validation; protected paths; operation preconditions; and distinct safe roots. Any mismatch enters a typed blocked/base-changed state without writes and invalidates stale staging/validation evidence.
5. Keep the backup → apply → postcondition → verified rollback sequence. Backups must include file bytes and modes for all affected paths. Check rollback of created/deleted/modified files and modes. A partial or uncertain rollback must persist `RecoveryRequired` with affected paths and operator actions. Record distinct requester, proposer, approver, and committer attribution where applicable.

**Acceptance tests:** a supplied ChangeSet file with another plan ID or altered digest is rejected; valid plan approval alone cannot apply; a preview-only ChangeSet cannot apply; a failed or stale validation cannot apply; changed source bytes, hidden files, Git HEAD, policy, or staged bytes abort before target writes; create over an existing file and delete of an absent file follow explicit preconditions; rollback restores bytes and modes or records `RecoveryRequired`; a complete happy path applies exactly the reviewed bytes once.

## Package 4 — Make Control API mutations real and durable (R03)

**Current code:** `application/control_service.py::approve_plan` and `apply_run`, `adapters/control_api/server.py`, API payload models, and broadcaster.

1. Replace the synthetic `RUN_APPLIED` branch with the same controlled apply application service used by the CLI. Fetch the persisted run, approved ChangeSet, staging manifest, validation evidence, identity, and policy. Return the actual `ApplyResult`; broadcast `RUN_APPLIED` only after persisted success. Map blocked, base-changed, rolled-back, and recovery-required outcomes to typed responses without claiming success.
2. Have API approval call the central approval service; do not manufacture a hash from the actor string. Bind the authenticated session to an independently resolved actor and authorize every privileged request.
3. Persist idempotency by `(actor, operation, resource, request_id, request-body digest)` in SQLite, not only a process-local dictionary. Reusing a request ID with a different body must fail. Concurrent duplicate requests must produce one mutation and one durable outcome.
4. Bound JSON body size and reject malformed bodies explicitly. Preserve exact Origin, session, and CSRF checks; do not use them as substitutes for policy authorization.

**Acceptance tests:** API apply changes a temporary target only with full valid evidence; no mutation occurs on missing approval or failed validation; broadcast and returned status match SQLite and filesystem state; duplicate and concurrent requests apply once; an idempotency key collision with different content fails; process restart returns the stored result.

## Package 5 — Enforce execution policy and redact outputs (R08, R12)

**Current code:** `adapters/command_runner.py`, `adapters/container_runner.py`, `application/validation.py`, validation profiles, and audit/report writers.

1. Require fixed framework-owned executable/argument templates and a verified staging root. An executable allowlist by itself is insufficient: arbitrary arguments to `python`, `node`, or package managers can execute arbitrary code. Run no command until the central policy authorizes its exact template, working root, and network class.
2. Make untrusted repositories static-analysis-only by default. If container execution is selected, fail closed when the engine is missing unless policy explicitly authorizes native fallback. Use a read-only container root filesystem, dropped capabilities, non-root user, no-new-privileges, network denied by default, and resource/time limits. Mount only the isolated staging area with the minimum write access needed for validation; never mount the authoritative source. Treat Windows/Podman differences explicitly.
3. Apply output limits during capture, including timeout paths, rather than only slicing after a complete capture. Redact sensitive diagnostics and previews before returning or persisting them. Keep a SHA-256 digest of complete output only if the complete byte stream can be hashed without unbounded memory. Do not log command arguments that contain secrets.

**Acceptance tests:** executable-allowed but argument-unsafe commands are denied; an untrusted repo cannot fall back to native execution; captured container invocation includes isolation flags and safe mounts; a synthetic secret in normal/timeout output never appears in result, audit, or report; output and runtime limits hold for a noisy or hung process. Tests use fake runners and command-vector inspection, not a required Docker daemon.

## Package 6 — Correct the bounded AngularJS migration slice (R09)

**Current code:** `adapters/transforms.py`, `application/transformation.py`, `tests/fixtures/angularjs-realworld-dashboard`, and transformation tests.

1. Write a supported-syntax contract for the fixture slice: component/directive registration, isolate bindings, local state, methods, `ng-if`, `ng-repeat`, `ng-click`, supported `$http` calls, template paths, and CSS. Mark every other construct unsupported with file and symbol evidence. Do not silently invent component names, endpoints, methods, or generic markup.
2. Carry source template and styles through the intermediate representation and use them in `render_template_html` and style rendering. Replace the current open-only `@if`/`@for` substitution with a structure-aware conversion that emits balanced blocks and valid expressions; reject constructs it cannot convert. Preserve displayed fields and action wiring from the source fixture.
3. Parse `$http` method bodies sufficiently to preserve verb, composed URL, path parameters, payload object, and return behavior. In particular, `updateStatus(userId, status)` must retain `userId` in the URL and `{ status: status }` as the body. Do not replace a missing endpoint with an invented `/api/v1/<method>` endpoint.
4. Generate unit tests that call only generated methods and assert actual behavior. Compile the generated components/services in a minimal pinned Angular fixture in an offline-capable test or CI gate. Keep extraction/rendering framework-specific in adapters.

**Acceptance tests:** golden outputs preserve the dashboard's role, department, activity limit, toggle actions, CSS, and HTTP request paths/payloads; generated `@if` and `@for` blocks are balanced; unsupported constructs return a typed failure and no ChangeSet; generated TypeScript/templates compile and generated tests run; the source fixture remains untouched.

## Package 7 — Serve a real offline Angular Control Center (R10)

**Current code:** `ui/control-center/`, `src/migration_agent/ui/static/`, packaging manifest, Control API server CSP.

1. Supply the Angular workspace entry point, build configuration, TypeScript configuration, and lockfile. Verify the Angular and TypeScript dependency versions together. Build the checked-in Angular source into the assets actually served by `agent ui`; remove the independent hand-written runtime or explicitly demote it to a test fixture.
2. Bundle Bootstrap CSS, Mermaid, and any other required runtime asset locally. Remove CDN references. Use Mermaid strict security and safe text rendering for untrusted repository content. Tighten CSP by removing `unsafe-inline`/`unsafe-eval` once the built application no longer needs them.
3. Wire typed API models to the actual server contract. Drive tabs, dialogs, approvals, run state, and WebSocket/SSE fallback through Angular state, with visible blocked/error outcomes. Do not show an applied state before the backend confirms a persisted result.
4. Update PyInstaller/release manifest inputs to include the actual build output and its checksums.

**Acceptance tests:** the production UI build succeeds; `agent ui` serves that build with network disabled; all CSS/JS requests are local and pass CSP; a real browser smoke test displays runs, diffs, a strict Mermaid graph, and accurate approve/apply outcomes; the packaged asset manifest validates offline.

## Package 8 — Make evaluation claims and documentation honest (R11)

**Current code:** `application/evaluation.py`, evaluation CLI, `docs/phase-status.md`, `docs/learning-log.md`, and master-plan status labels.

1. Separate discovery precision/recall from transformation correctness. Keep component-name detection metrics, but label them accurately. Add independent golden and compile/runtime metrics for the supported AngularJS slice, including negative and unsupported cases. Report sample counts and fixture scope beside every score.
2. Run baseline and specialist paths independently. Measure actual output quality, turns, latency, cost, and repair outcomes; never copy baseline F1 into specialist F1 or hard-code repair accuracy. Declare improvement only from a measured comparison under predeclared criteria.
3. Reconcile the master plan's stale phase diagram/status labels and add an authoritative Phase 11 acceptance section or a linked amendment. Update Phase 10/11 claims only after the corresponding gates pass. Document residual limitations and unsupported syntax rather than calling a small fixture a general real-world AngularJS migration.

**Acceptance tests:** deliberate omission and false-positive examples lower discovery metrics; broken generated code lowers transformation metrics; specialist metrics differ only when the executed specialist path differs; report schema includes sample counts and limitations; documentation cites actual gate output.

## Final integration and completion criteria

Run these from the integrated tree after resolving Phase 12 conflicts:

```text
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run migration-agent doctor
```

Also run an offline Angular production build, the controlled-apply happy and adversarial fixture tests, the UI/browser smoke test, and the AngularJS migration evaluation described above. Re-run the security regression tests on Windows and Linux. Record exact command results, failing/skipped counts, and environment limitations. Confirm `git diff` contains only intended remediation plus explicitly integrated Phase 12 changes, and that source fixtures and unrelated user files were not modified.

**Stop condition:** Complete the remediation when every release gate above has evidence and `docs/phase-status.md` reflects the verified state. If a gate cannot run, leave that item open with the exact blocker; do not mark Phase 10 or 11 fully remediated.
