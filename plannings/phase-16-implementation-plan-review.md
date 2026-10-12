# Review findings for the Second Wave implementation plan

Reviewed: 2026-10-04  
Source: `C:\Users\vkumar\.gemini\antigravity\brain\7a712a9d-3abf-40c9-b956-2a25f5e24a5f\implementation_plan.md` (lines cited below)  
Purpose: Changes to incorporate into the plan before Phase 16 implementation. This document is a plan review; it does not declare Phase 16 complete or change its implementation.

## Overall assessment

Phases 13–15 in the proposed plan substantially match the recorded implementation in [phase status](../docs/phase-status.md). Phase 16 has a useful objective: expose the existing application services through an ambient coding-agent interface while preserving CLI state. Its current design is not ready for implementation because it conflates a host model's tool arguments with human authorization, assumes unsupported protocol behavior, and promises recovery and client compatibility without defining the state and transport contracts needed to prove them.

The [master plan](final/agent-platform-master-plan.md) is authoritative. Its invariants 1, 5–7, 19–26, 28 and 40 must remain true through MCP. The MCP adapter is a new untrusted client boundary, not a new approval authority.

**Priority legend:** P0 = must resolve before any mutating MCP tool; P1 = must resolve before Phase 16 completion; P2 = accuracy, packaging, or scope improvement. “Plan” line numbers refer to the external source above. Code references are to the repository at review time.

## Findings to incorporate

### P0-1 — Remove model-supplied approval and identity shortcuts

**Evidence:** Plan lines 109, 127–129 propose `auto_approve: bool` and `actor` arguments for MCP mutation. The current [pipeline](../src/migration_agent/application/orchestration.py) approves a plan with Mode B if `auto_approve` is true (lines 429–458), then proceeds to apply (lines 583–590). An MCP host can generate tool arguments; those arguments are not proof of a human approval or actor identity. Master-plan invariants 5, 19 and 22 distinguish authentication, capability authorization and a human approval bound to an exact ChangeSet digest.

**Plan change:** Delete `auto_approve`, caller-controlled `actor`/`by`, and any secret-bearing `session_token` from model-callable tool schemas. Resolve identity through the existing trusted session/identity port and check capability for each action. Require an independently verified human approval for the exact ChangeSet and current policy/base before apply. Provide an **in-IDE approval path** where the host can present a trusted, human-operated review surface; otherwise return `APPROVAL_REQUIRED` with the digest and a local review link or CLI path. Do not treat a model-generated tool call, tool text, sampling response, generic MCP permission prompt, or an agent's “yes” as a signature. Define how Mode A actions remain inaccessible to a Mode B/C session.

**Acceptance:** An engineer can review and approve inside a supported IDE without leaving chat, while a model can call every advertised tool with forged actor names and `true` values without producing an approval or applying. A stale/altered ChangeSet, policy, base or signatory fails closed. The audit distinguishes requested, proposed, approved and committed actors.

#### P0-1 clarification — Evaluate Gemini's `migration_sign_approval(plan_id, session_token)` proposal

Gemini is right about the usability concern: requiring a terminal for every step is unnecessary. The proposed tool signature is still unsafe. MCP tool arguments are model-visible/model-controllable; if the token is passed there, the model can replay or disclose it. If the server reads a pre-shared token from the IDE environment whenever the tool is called, the model can call the tool without a human review event. Possession of a bearer token authenticates a session; it does not prove that a human approved this specific diff. A server signing on the caller's behalf with its own key likewise does not establish human intent. This distinction follows the master plan's identity/signing separation and invariants 19, 22 and 29.

**Preferred design:** A model-callable `migration_request_approval(changeset_id)` may prepare a review request, returning only a non-secret request ID and summary. A **trusted host UI or local platform approval UI** displays the exact files/diff, ChangeSet digest, base fingerprint, policy digest, validation result and requested capability, then captures an explicit human action through a channel the model cannot script or read. That channel submits a one-use, short-lived approval assertion bound to the digest, action, project, actor/session and nonce. The server verifies it independently and persists the approval. `migration_step_apply` accepts only the persisted approval reference/ChangeSet ID; it never accepts a secret or boolean as proof. If the IDE cannot expose a verifiable human-only callback, open the local review UI from the IDE or use the existing CLI/GUI path. For Mode A, use the configured SSH/GPG signing mechanism; a Mode B session token must never be upgraded into Mode A authority.

**Do not assume MCP elicitation itself authenticates the human.** The current MCP protocol supports user-input round trips, including confirmation flows, but an elicitation response is still client-supplied input and must be tied to a trusted host action or separate signer before it satisfies this project's approval invariant. See the [2026-07-28 MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/) and [SDK guidance on multi-round-trip input](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28).

**Required tests:** (1) model calls request/complete/apply without human action; (2) token appears in model tool arguments or logs; (3) same assertion replayed or used on another ChangeSet/project/action; (4) approval after diff, base, policy or validation changes; (5) Mode B assertion used for Mode A action; (6) genuine IDE approval followed by successful apply. All first five must fail closed; the last must succeed without a terminal on a supported host.

### P0-2 — Make validation and dirty-tree policy non-bypassable through MCP

**Evidence:** Plan lines 84–85 and 128 inherit `--skip-validation`/`--allow-dirty`/automatic approval ideas from Phase 15. In the current [pipeline](../src/migration_agent/application/orchestration.py), `skip_validation=True` leaves `all_passed=True` (lines 510–515) and reaches `apply` (lines 583–590). `allow_dirty=True` skips the preflight clean-tree check (lines 402–403). The master plan requires validated staging and comprehensive drift invalidation (invariants 6, 25, 28).

**Plan change:** Do not expose these bypasses in MCP. Record validation provenance against the exact staged ChangeSet, profile, commands and policy version. Apply only when required gates passed; distinguish `NOT_RUN`, `UNAVAILABLE`, `FAILED` and `PASSED`. Treat dirty source state as `BASE_CHANGED` until re-inspected and re-planned. If a narrowly scoped developer override is retained for CLI, document its restricted environment and ensure it cannot authorize final apply.

**Acceptance:** `skip-validation` or unavailable commands cannot be interpreted as passing validation by MCP; dirty/untracked source files block apply even when a caller attempts a bypass.

### P0-3 — Do not accept arbitrary filesystem paths as authority

**Evidence:** Plan lines 121–133 accept `path`, `output_dir`, `staging_path` and `changeset_file` in tool calls. A host/model can choose those values. The master plan requires source, staging and artifact separation, symlink-safe containment and protected path policy. A `changeset_file` supplied by a caller is not a verified persisted ChangeSet.

**Plan change:** Bind the server to a registered project root at launch or an explicit server-side project registration step. Use server-minted opaque `project_id`, `run_id`, `step_id` and `changeset_id` for subsequent tools; fetch persisted records through application ports. Avoid caller-specified staging/output roots for privileged tools. Validate canonical paths, reparse points/symlinks, overlapping roots, relative POSIX paths, file modes, size and protected paths at the application boundary, not only in tool schema. Treat returned repository content and diagnostics as untrusted text.

**Acceptance:** Traversal, symlink escape, alternate project, arbitrary changeset file, source/staging overlap and out-of-root output attempts are rejected before side effects on Windows and Linux.

### P0-4 — Specify a safe cross-interface state machine, not “resume at any point”

**Evidence:** Plan lines 11, 95–96 promise lossless mid-run handoff at any point. Lines 110 and 158–165 only propose status display and four broad handoff tests. Existing [resumption](../src/migration_agent/application/orchestration.py) and SQLite checkpoints do not by themselves make an in-flight apply or a partially completed external command safely transferable. Master-plan invariant 28 requires explicit crash reconciliation and `RECOVERY_REQUIRED` when rollback is uncertain.

**Plan change:** Define transfer only at durable, quiescent boundaries: plan saved, preview saved, stage verified, validation result persisted, approval recorded, apply completed/rolled back. Persist an operation/step state with generation, owner, request ID, base fingerprint, policy digest and ChangeSet digest. Use a single-writer claim/lease or transaction for every mutating transition. On takeover, reconcile actual disk and checkpoint state before advancing. Never auto-resume an ambiguous `APPLY_INTENT`; return `RECOVERY_REQUIRED` where verification cannot prove a safe continuation. A dirty worktree status is diagnostic, not a drift mitigation.

**Acceptance:** Concurrent CLI and MCP requests cannot stage or apply the same step twice. A crash after patching but before response is classified by disk inspection. Stale validation/approval is invalidated after any base, policy or ChangeSet change. Handoff is documented as supported at named checkpoints, not arbitrary instruction boundaries.

### P0-5 — Separate interactive host reasoning from `AgentRuntimePort`

**Evidence:** Plan lines 106 and 135–143 describe “tool-driven inversion” as a fallback implementation of `AgentRuntimePort`. The existing [port](../src/migration_agent/ports/agent_runtime.py) has synchronous `analyze`, `plan` and `ask` methods returning typed results. A host agent reasoning in chat cannot synchronously satisfy that port when an MCP client provides only tool calls. The proposed Tier C silently mixes configured live SDKs and fake output into a “zero separate API keys” path.

**Plan change:** Define two explicit operating modes. **Host-orchestrated mode:** expose deterministic inspect/preview/status tools and a typed `submit_analysis` or `submit_plan_proposal` command if host-generated input is genuinely needed; validate all submitted evidence and provenance as untrusted. **Server-runtime mode:** use an explicitly configured provider adapter with its ordinary credential requirements. The deterministic fake is test-only, never a production fallback. Do not promise automatic continuity of a model thought process between CLI and host; only persisted, typed run artifacts transfer. Keep provider SDK and MCP types out of domain/application contracts.

**Acceptance:** A no-credential host session can complete only the documented host-orchestrated flow; a server-runtime request without credentials returns a clear configuration error; no fake result is presented as a real analysis.

### P0-6 — Reconcile Phase 16 with the current MCP protocol before choosing a transport/runtime

**Evidence:** Plan lines 106, 108, 116–118 and 139–142 assume sampling as a preferred mechanism and progress notifications as a timeout reset. The official [2026-07-28 MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/) deprecates sampling and moves durable long-running work into the Tasks extension; it also changes the protocol lifecycle. The [Python SDK documentation](https://py.sdk.modelcontextprotocol.io/v2/handlers/sampling-and-roots/) warns new servers against building on sampling. The [Tasks extension](https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks) defines task handles, polling and cancellation. Progress notifications convey progress but do not impose a universal client timeout-reset rule.

**Plan change:** Pin a supported protocol version and Python MCP SDK version after a compatibility spike. Treat sampling as optional legacy interoperability only, not a required Tier A path. For long validation, either use the Tasks extension when negotiated or a server-owned durable operation ID with `start/status/cancel` tools and bounded calls. Specify cancellation semantics, process exit, retries and result retention. Use official SDK transport/framing and error handling instead of an unspecified hand-written JSON-RPC server. Test both modern and legacy clients if both are claimed.

**Acceptance:** A client that never supports sampling or progress can complete the supported flow. A 2-minute validation does not require a held-open request. Disconnect/reconnect can retrieve the final state by durable ID. Unsupported protocol features return a clear capability error.

### P1-7 — Treat `stdio` isolation as an end-to-end process property

**Evidence:** Plan line 107 correctly flags stdout corruption, but checking that one command runner uses `capture_output=True` is insufficient. Imports, framework logging, CLI banners, warnings, child processes and shutdown hooks can write to stdout. The current [command runner](../src/migration_agent/adapters/command_runner.py) captures direct child output (lines 134–139), but the server entry point must be isolated independently. The [Python MCP SDK logging guidance](https://py.sdk.modelcontextprotocol.io/handlers/logging/) also notes that unflushed prints can still reach the wire.

**Plan change:** Reserve process stdout exclusively for MCP frames from startup through shutdown; configure all logs to bounded/redacted stderr, and capture child stdout/stderr. Launch through a dedicated `mcp serve` entry path with no CLI rendering. Test with a real subprocess transport, import-time warning, command failure, cancellation and shutdown. Do not print tokens, secrets, source snippets or raw diagnostics to stderr.

**Acceptance:** Every stdout byte is valid for the selected MCP transport across normal and failure cases; secret fixtures never appear in stdout/stderr or persisted audit.

### P1-8 — Define tool effects, capabilities and response contracts

**Evidence:** Plan lines 119–133 list fourteen tools but do not classify side effects, required capabilities, result schemas or error states. `adopt`, `plan`, `stage`, `record_decision`, `resume` and `apply` can mutate governance, staging, checkpoints or source. `ask` can send source context to a remote provider. The master plan requires typed public boundaries and policy enforcement for privileged operations.

**Plan change:** Add a per-tool table with input/output Pydantic models, side-effect class, capability, assurance level, approval requirement, allowed run states, idempotency key, timeout/cancellation policy and maximum result size. Use structured error codes such as `APPROVAL_REQUIRED`, `BASE_CHANGED`, `POLICY_BLOCKED`, `VALIDATION_REQUIRED`, `RECOVERY_REQUIRED` and `UNSUPPORTED_CAPABILITY`. Keep the initial Phase 16 surface narrow: doctor, inventory/status, saved plan/preview, and guarded stage/validate/apply/resume only if their preconditions are fully implemented. Add Q&A and ADR writing only when separately justified within the requested phase.

**Acceptance:** Tool discovery exposes typed schemas and a documented effect/capability matrix. Unauthorized or invalid-state calls have no side effect and return stable machine-readable errors.

### P1-9 — Make retry and cancellation semantics explicit

**Evidence:** Plan lines 108, 124–129 lack request IDs and cancellation behavior. A client can retry after timeout or reconnect while the first call is still running. The master plan's invariant 40 requires idempotency for mutating control operations; the current Control API has an in-memory cache, which is not sufficient for cross-process CLI/MCP retry after a crash.

**Plan change:** Require a client-generated request ID for every mutating operation and persist the operation outcome in SQLite transactionally with state changes. Replays with the same ID and same parameters return the stored result; same ID with changed parameters rejects. Cancellation may stop only at safe boundaries and must never cancel the audit/reconciliation needed after apply intent. Define operation TTL and status retrieval.

**Acceptance:** Duplicate `stage`, `validate`, `approve` and `apply` requests across process restart cannot repeat side effects. Cancel during build records a terminal/cancelled validation outcome; cancel during apply resolves to applied, rolled back or recovery required.

### P1-10 — Specify execution safety inherited from Package 5

**Evidence:** Plan lines 125–126 propose headless validation, but omit the command and container isolation requirements. The master plan requires allowlisted executable/arguments, sanitized environments, staging-only execution, timeout/resource bounds and restricted defaults for newly adopted repositories (Section 15). An MCP tool call must not create a new path to invoke arbitrary commands or downgrade isolation.

**Plan change:** `step_validate` accepts a server-defined profile ID, not a command string or caller-selected staging path. Route through the existing policy engine and command runner with the same containment, sanitized environment, timeout, output caps and container policy as CLI. Reject untrusted repository package scripts unless explicitly allowed by project policy and operator approval. Include platform-specific behavior for Windows/Linux and unavailable container engines. Never silently fall back from required container isolation to local execution.

**Acceptance:** MCP cannot execute a raw model command, choose a different working directory, inherit credentials, or run with weaker isolation than the equivalent CLI action.

### P1-11 — Add data privacy and prompt-injection boundaries

**Evidence:** Plan lines 106, 130 and 139–143 move repository context through a host model or provider but do not specify disclosure limits. Source files and diagnostics can contain secrets or malicious instructions. MCP tool output can itself steer an ambient agent.

**Plan change:** Define eligible file classes, secret exclusion/redaction, per-tool byte caps, bounded context envelopes and data-egress disclosure for host versus provider mode. Return evidence references rather than full files by default. Treat source text, comments, generated diffs and diagnostics as untrusted data; no instruction in them can authorize a new tool action. Log digests/metadata rather than raw prompts and outputs. Require explicit user-facing provider selection where remote data transfer occurs.

**Acceptance:** Tests with secret-name files, credential patterns, injected “ignore policy” text and oversized diagnostics show no secret disclosure or authority escalation.

### P1-12 — Replace broad compatibility claims with a measured matrix

**Evidence:** Plan lines 11, 96, 106 and 148–155 promise 100% interoperability and native integration across named hosts, but no client/version/OS/protocol matrix is defined. The list is internally inconsistent: Codex appears in the goal, Windsurf appears in a rationale, and setup supports only Antigravity, Cursor and Claude. A local skill or slash-command directory is not automatically portable across hosts.

**Plan change:** List exact supported clients, versions, operating systems, MCP protocol revisions and required capabilities. Separate (a) generic MCP tools, (b) optional client configuration generator, and (c) client-specific skill/command files. Mark untested clients as experimental. Remove “100%” and “one click” language until the matrix is demonstrated. Add a manual config example for every claimed client.

**Acceptance:** Each supported row has a smoke test or reproducible manual checklist covering install, discovery, tool call, restart and removal. Documentation only advertises tested combinations.

### P1-13 — Make setup and skill installation safe and reversible

**Evidence:** Plan lines 147–155 allow automatic modification of external client config and write skills into `.agent/`. Existing `.agent/` is Git-governed project data, while external host config is user data. Both writes need exact target selection and merge behavior.

**Plan change:** Make `agent mcp setup --client ...` a preview/print operation by default. For an explicitly requested install, identify the exact config file, validate its schema, preserve unrelated entries, write atomically with backup, and provide an uninstall/check command. Do not hardcode a `uv run` invocation that depends on the caller's current directory; use an installed executable or absolute, safely quoted launch arguments. Place optional skills in client-appropriate locations only after explicit selection. Do not let skill text become a security control; the application must enforce the rules.

**Acceptance:** Existing client configuration survives setup and removal byte-for-byte except for the owned entry. Invalid config is not overwritten. Launch works when the client starts outside the repository and when the path contains spaces.

### P1-14 — Expand verification beyond protocol happy paths

**Evidence:** Plan lines 158–165 cover discovery/call, two handoffs, dirty tree and sampling. They omit attack, crash, concurrent and long-operation cases. The proposed `migration_status` test would only show a dirty path, not prove safe handoff.

**Plan change:** Add offline tests for schema validation, malformed JSON, unsupported version/capability, no-sampling host, process startup/shutdown, stdout purity, bounded output, secret redaction, path escape/symlink, forged actor/approval, stale policy/base/validation, changed ChangeSet after repair, duplicate request, concurrent CLI/MCP writer, crash at every apply checkpoint, client disconnect, cancellation, command/container policy and Windows/Linux path behavior. Use the real transport/SDK in contract tests and deterministic fake analysis data. Add one end-to-end flow per *supported* host mode; never require network/API keys for normal tests.

**Acceptance:** Failure tests prove no unauthorized source mutation; both-direction checkpoint handoff succeeds; ambiguous apply enters `RECOVERY_REQUIRED`; all required repository quality gates pass.

### P2-15 — Correct status and evaluation language

**Evidence:** Plan line 5 calls 345 passing tests “quality gates”; there are six required quality-gate commands, and [phase status](../docs/phase-status.md) records **345 passed, 2 skipped** for Phase 15. Plan line 55 omits the two skipped Phase 13 tests. Lines 8 and 86–89 imply deep AST transformations and compilation/spec pass metrics, while Phase 15's recorded implementation checks delimiter/declaration structure and Jasmine marker presence rather than running a TypeScript compiler or tests. The [master plan](final/agent-platform-master-plan.md) specifies Angular 21 LTS as the Control Center baseline; generated targets are described elsewhere as Angular 17+, so the target compatibility range must be explicit.

**Plan change:** Say “345 tests passed, 2 skipped; six required gate commands passed” for Phase 15. Do not call structural checks compilation or spec pass rates; rename to `typescript_structure_rate` and `spec_structure_rate`, or implement actual offline `tsc`/Angular test execution against a pinned fixture before using those labels. Distinguish GUI Angular baseline from generated-target compatibility. Replace “production-grade”, “tamper-resistant”, “full template migration” and “lossless” with claims tied to adversarial, compile and integration evidence. State that existing phase records are historical and Phase 16 completion is pending.

**Acceptance:** Every completion/quality claim maps to a recorded command result or test. No structural heuristic is reported as a compiler/test pass.

### P2-16 — Clarify phase boundary and dependency sequence

**Evidence:** The [master plan](final/agent-platform-master-plan.md) contains phase playbooks through Phase 10; the proposed plan adds Phases 13–16. Plan lines 116–175 bundle transport, reasoning, 14 tools, host installers, skills and documentation into one phase without explicit cut lines. Repository instructions require only the requested phase, no speculative future infrastructure, and stopping after its gates/documentation.

**Plan change:** Add a Phase 16 addendum to the authoritative architecture or explicitly state how this subordinate plan is governed by it. Split Phase 16 into ordered deliverables inside the same phase: **16A** transport/protocol and read-only tools; **16B** persisted operation IDs, locks and safe handoff; **16C** guarded mutations and approval integration; **16D** optional host setup/skills and compatibility documentation. Each deliverable needs entry/exit criteria. Keep unsupported clients, speculative adapters and provider migration outside Phase 16 unless required to meet the defined goal.

**Acceptance:** A developer can implement the phase in order without needing to invent a security model or build future-phase infrastructure. `docs/phase-status.md` is updated only after the final Phase 16 gates pass.

## Recommended revised Phase 16 contract

1. **Goal:** A local MCP server exposes selected existing application operations to tested clients. CLI and MCP share persisted run artifacts and can resume at defined durable checkpoints. All source mutations retain the same identity, approval, policy, validation and controlled-apply requirements.
2. **Supported modes:** Host-orchestrated tools without server API credentials; configured server-runtime mode using the existing provider adapter. Sampling is optional compatibility behavior only where supported and justified by a pinned protocol version. Fake runtime is for tests.
3. **Initial tools:** `doctor`, `inventory`, `run_status`, `plan_show`, `step_preview`, `operation_status`; add `plan_create`, `step_stage`, `step_validate`, `step_apply` and `run_resume` only after P0/P1 preconditions above are enforced. Add `request_approval` for a tested trusted IDE/local UI flow, with no secret-bearing model arguments. Use server-minted handles and typed results. Avoid arbitrary path/file and approval booleans.
4. **Long work:** Return a durable operation handle; support polling and cancellation at safe boundaries. Use the official Tasks extension only when negotiated, with a documented fallback for clients without it.
5. **Handoff:** Allowed only at named persisted states, with a single writer, idempotent mutation calls, disk reconciliation and explicit `BASE_CHANGED`/`RECOVERY_REQUIRED` outcomes.
6. **Completion evidence:** Offline contract, adversarial and integration tests; tested client matrix; no credentials in normal tests; all required repository gates (`uv sync --all-groups`, `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run migration-agent doctor`), plus the `agent doctor` alias smoke check; documentation and phase status synchronized after success.

## Suggested order for editing the source plan

1. Rewrite executive claims and Phase 16 goal using P2-15 and the revised contract.
2. Replace the five-risk table with the P0 trust, state, protocol and execution risks above.
3. Replace the 14-tool list with a typed effect/capability matrix and staged tool surface.
4. Replace the ambient runtime fallback section with the explicit two-mode design.
5. Replace timeout and handoff language with durable operations and checkpoint state machine.
6. Add the adversarial verification matrix, client support matrix and phase exit criteria.

