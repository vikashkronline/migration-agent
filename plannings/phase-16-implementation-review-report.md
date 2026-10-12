# Phase 16 implementation review

**Review date:** 2026-10-04  
**Repository:** `C:\Projects\New folder\migration-agent`  
**Reviewed baseline:** HEAD `5ab1b62` plus the current uncommitted implementation.  
**Reference plan:** `C:\Users\vkumar\.gemini\antigravity\brain\7a712a9d-3abf-40c9-b956-2a25f5e24a5f\implementation_plan.md`  
**Other requirements:** `AGENTS.md`, `plannings/final/agent-platform-master-plan.md`, and `docs/phase-status.md`.

## Remediation update — 2026-10-04

The findings and reproduction results below describe the **original reviewed implementation**. Following user authorization, the implemented Phase 16A boundaries and shared code were corrected and regression coverage was added. **R01–R09 and R11 are remediated in code.** R10 documentation has been corrected; actual Antigravity/Codex observations remain pending. C01 remains a coverage gap because 16B–16D have not been implemented in this remediation.

All six required quality gates passed; the final test result is **402 passed, 2 skipped**. See [the remediation decisions](../docs/phase-16a-remediation.md), [recorded gate evidence](../docs/phase-status.md), and section 8 for the current disposition. Original line references and failure descriptions are historical evidence, not claims that the corrected checkout still exhibits those failures.

## 1. Conclusion

The implementation is a useful MCP foundation, but **the complete Phase 16 plan has not been executed in this checkout**. Only the five inspection tools from **16A** exist. The phase status document itself records only 16A as complete. The host proposal loop, durable operation handles, guarded approval/apply protocol, setup commands, and actual Antigravity/Codex workflow verification from **16B–16D remain outstanding**.

Even 16A needs remediation before accepting its project containment and secret protection claims. Four high priority defects were reproduced: records from another project can be returned and previewed; operational state can be written inside the source repository; preview reads can escape the source through symlinks; and secret-shaped content can reach MCP results and persisted ChangeSets.

The existing automated checks pass. They provide evidence of normal transport and schema behavior, but do not test the failing boundaries identified below. There is no finding requiring a new GUI: the final plan explicitly defers the full GUI and requires a headless workflow.

**Recommendation:** correct R01–R06 and the policy/evidence gaps before closing 16A, then implement 16B, 16C, and 16D as separately gated milestones. Do not expose mutation tools until their shared application gates exist.

### Severity and evidence conventions

- **P1:** source isolation or data protection defect; fix before accepting the affected feature.
- **P2:** correctness, contract, operability, or verification gap; address in the indicated milestone.
- **Reproduced:** executed against disposable local fixtures during this review.
- **Inspection:** established from the current code or documentation; no failure beyond the stated observation is claimed.
- **Coverage gap:** a planned deliverable is absent; this is distinct from an implemented feature behaving incorrectly.

## 2. What is implemented and what remains

| Milestone | Current evidence | Assessment |
|---|---|---|
| **16A: MCP transport and inspection** | MCP dependency, `mcp serve`, project binding, five typed tools, extracted doctor service, nine contract tests | Implemented in part; containment, response protection, failure handling, and measured host approval spike need correction |
| **16B: durable operations and host proposals** | No MCP proposal submission, operation status/cancel, request deduplication, or new lease/lock lifecycle found | Outstanding |
| **16C: guarded approval and apply** | No `ApplyApprovalRecord`, exact-ChangeSet human review flow, unified new apply gate, or MCP stage/validate/apply tools found | Outstanding |
| **16D: setup, skills, client verification** | No `mcp setup` implementation or Phase 16 host instruction packaging found; no measured primary-client workflow evidence | Outstanding |

The server currently registers exactly:

1. `migration_doctor`
2. `migration_inventory`
3. `migration_run_status`
4. `migration_plan_show`
5. `migration_step_preview`

### C01 — P1 coverage gap: the complete plan is not delivered

The current MCP interface can inspect an existing migration plan. It cannot support the required complete host journey from inventory/evidence through host analysis, proposal validation, staging, validation, repair, human approval, and controlled apply.

The remaining work includes:

| Area | Required deliverables still outstanding |
|---|---|
| Host reasoning | Bounded evidence read; typed analysis, plan, and repair proposal submission; deterministic evidence/symbol/scope/DAG validation |
| Durable operations | Persisted `operation_id`, request idempotency, status/cancel, reconciliation after disconnect or restart |
| Concurrent execution | Exclusive OS apply lock, SQLite lease, monotonic generation, ownership/expiry checks across individual writes |
| Lifecycle | Complete 12-state transition enforcement, drift invalidation, `APPLY_INTENT` startup reconciliation, explicit ambiguous recovery |
| Approval | Exact-ChangeSet `ApplyApprovalRecord`, human review challenge, out-of-band approval storage, trusted identity/policy enforcement |
| Apply gate | Shared application preconditions across CLI and MCP, validated provenance, clean base, rejection of bypass flags during final apply |
| Client usability | Preview-first setup generation and atomic backed-up writes, Antigravity skill, Codex instruction pack |
| Verification | Actual Antigravity and Codex smoke evidence, complete standalone journey, documentation synchronization |

Existing trust domain models, rollback/recovery behavior, checkpoints, CLI workflows, and UI files are useful prerequisites. Their presence does **not** demonstrate the new Phase 16 contracts. For example, `TransformationService.apply` still checks a legacy plan approval; it does not verify the planned `ApplyApprovalRecord`. Existing `RECOVERY_REQUIRED` references do not establish the new 12-state engine or startup intent reconciliation.

**Action:** distinguish “16A implementation delivered” from “Phase 16 complete.” Resume 16B only after the 16A remediation gate. Preserve the independent standalone runtime route while adding the host route. No GUI phase is needed to complete this work.

## 3. Findings in the implementation

### R01 — P1: stored plans and runs are not scoped to the bound project

**Evidence:** reproduced.  
**Locations:** `src/migration_agent/adapters/mcp/tools.py:85`, `:125`, `:161`.

The handlers validate the caller-supplied `project_id`, then fetch a run or plan by its global ID from the shared SQLite store. They never compare the retrieved record's `source_root` with `binding.project_root`.

With a server bound to project A and a shared store containing project B's records:

- `handle_plan_show(A, A.project_id, B.plan_id, store)` returns B's full plan, labeled with A's project ID.
- `handle_run_status(A, A.project_id, B.run_id, store)` returns B's run and roots.
- `handle_step_preview` accepts B's plan but transforms A's source and saves the resulting ChangeSet.

This is both disclosure across projects and incorrect association of migration intent with source content. Knowing a record ID is sufficient; traversal characters are unnecessary.

**Remediation:** validate canonical ownership immediately after every lookup, including governance-file fallback. Prefer project-scoped persistence lookups and keys. Verify the related plan/run/step ownership before generating or persisting a preview. Do not use the response's outer project ID to relabel an unrelated object.

**Acceptance tests:** two projects sharing one state directory; foreign plan, run, and preview requests must fail with a stable project-mismatch/not-found error, disclose no foreign record, and create no ChangeSet.

### R02 — P1: a read-only server can write operational files inside the source

**Evidence:** reproduced.  
**Locations:** `src/migration_agent/adapters/mcp/server.py:71`, `src/migration_agent/adapters/mcp/tools.py:158`, `src/migration_agent/adapters/checkpoints.py:35`.

`create_mcp_server` constructs a writable `SqliteCheckpointStore` without checking that its state directory is separate from the source. Setting `--state-dir` to the source root creates `checkpoints.db` there during server construction, before a tool call. Environment-configured state paths have the same gap.

The preview handler's fallback is additionally incorrect: it passes `<source>/.agent/checkpoints.db` as a **directory** to a constructor expecting a state directory. Even a request for a missing plan creates:

```text
<source>/.agent/checkpoints.db/checkpoints.db
```

The registered tool supplies a store, so that fallback is not the ordinary MCP route; it is still an unsafe exported handler path. The configured state/source overlap is directly reachable through `mcp serve`.

**Remediation:** resolve and validate the complete source/staging/state/artifact root relationships before constructing any writer. Reject equality and unsafe ancestor/descendant overlaps, including link aliases. Require an injected validated store or use the configured out-of-source state directory; remove the source-local fallback.

**Acceptance tests:** state equal to, inside, and containing source; relative paths; environment overrides; link aliases; missing-plan fallback. Rejection must occur before any directory, database, or journal is created. Ordinary reports and out-of-source state records remain permitted without migration approval.

### R03 — P1: preview bypasses the safe file reader and follows outside-root links

**Evidence:** reproduced on Windows using synthetic files.  
**Locations:** `src/migration_agent/application/transformation.py:112`, `:122`; `src/migration_agent/adapters/transforms.py:59`, `:63`, `:65`, `:153`, `:191`, `:204`; `src/migration_agent/domain/changeset.py:90`.

The safe inspector is used for framework detection, but the actual transformation discovers and reads files independently. Component/template/style reads use ordinary `Path.read_text`, and fingerprinting separately uses `read_bytes`. These paths do not consistently enforce the inspector's containment, link, secret-file, ignore, and size rules.

In a disposable Ember fixture, replacing `app/styles/app.css` with a symlink to an outside-root CSS file caused the extractor to read the external content. Replacing the component template with a symlink to an outside-root template caused its marker text to appear in the MCP preview diff. The source was still the canonical bound project; no malicious tool path parameter was needed.

`ProjectBinding.resolve_in_project` cannot protect this path because the actual reads do not use it. Manifest and governance plan reads also use ordinary file reads and need the same link-containment review.

**Remediation:** enforce eligible-file and canonical-root checks at every actual read, including companion files and fingerprint inputs. Prefer an inspected snapshot or a guarded filesystem port over rediscovery. Reject link/reparse-point escapes and excluded files; do not silently fall back to reading them. Apply source size limits before loading content.

**Acceptance tests:** symlinked JS, template, style, manifest, and plan; outside-root directory links/junctions where supported; ignored and secret-like files; oversized companions; the inventory and preview paths must apply the same file policy. No outside marker may enter results or persistence.

**Scope:** parts of this flaw predate 16A. The new MCP preview exposes the inherited behavior and must not advertise containment until it is enforced end to end.

### R04 — P1: redaction protects logs but not tool results or generated artifacts

**Evidence:** reproduced with a fake token, not a real credential.  
**Locations:** `src/migration_agent/adapters/mcp/server.py:33`, `src/migration_agent/adapters/mcp/tools.py:132`, `:188`, `src/migration_agent/application/transformation.py:284`.

`RedactingStreamHandler` only processes logging output. Tool handlers return full plans and raw diffs without applying response redaction or secret detection.

A synthetic token recognized by `RedactionPolicy.redact_text` was returned unchanged in a plan step description. Placing that token in a template routed through the renderer also returned it in the preview diff and persisted it in the generated ChangeSet content. The current subprocess test only calls doctor, so it does not detect this.

**Remediation:** validate/redact user-visible plan metadata, evidence, errors, and diffs at the MCP boundary. Reject or explicitly block secret-bearing generated content **before** saving artifact bytes. Preserve exact ChangeSet digest semantics: do not silently change executable content after calculating its digest. Redacted display data should identify itself as a redacted view.

**Acceptance tests:** synthetic token patterns in plan descriptions/evidence, generated template content, errors, logs, and transport responses. Verify both result representations used by the SDK and durable state. No secret-shaped fixture value may survive in a persisted generated artifact.

### R05 — P2: an unknown step ID expands to an unrestricted preview

**Evidence:** reproduced.  
**Locations:** `src/migration_agent/adapters/mcp/tools.py:168`, `src/migration_agent/application/transformation.py:135`.

The handler checks step ID syntax but not membership in the plan. The application lookup returns `None` for an unknown ID; its matching helpers then accept every discovered component/service.

Requesting `nonexistent-step` against a plan containing only `step-one` returned `status="ok"`, generated four files in the test fixture, and persisted a ChangeSet for the nonexistent step. In a larger repository, the matching logic allows the whole discovered set. Whitespace-only IDs also lack an explicit invalid-ID contract.

**Remediation:** distinguish intentional plan-wide preview from a requested step preview. Reject missing, blank, duplicate, or unknown step IDs before reading or generating source-derived artifacts. Check authoritative step scope rather than treating a failed lookup as unrestricted scope.

**Acceptance tests:** nonexistent and whitespace IDs return a typed error and save nothing; a valid step generates only its authorized files; omitted-step behavior is explicit and consistent in result metadata and the saved ChangeSet.

### R06 — P2: shutdown/error handling masks the original transport exception

**Evidence:** reproduced.  
**Location:** `src/migration_agent/adapters/mcp/server.py:191`.

The exception tuple calls `anyio.get_cancelled_exc_class()` after `anyio.run` exits. At that point there is no active async event loop. When a synthetic transport failure was raised, the caller received `NoEventLoopError` instead of the original failure. The intended generic exception logger and exit path were bypassed. The same tuple is evaluated for a `KeyboardInterrupt`.

**Remediation:** handle synchronous `KeyboardInterrupt` separately. Handle async cancellation inside the running async wrapper, where the backend cancellation class is available. Put relevant initialization failures under a defined stderr-only startup error path.

**Acceptance tests:** normal EOF/disconnect, Ctrl+C, invalid startup configuration, and a transport exception. Assert expected exit behavior, preserved useful diagnostics, no secondary event-loop exception, and zero non-protocol stdout.

### R07 — P2: project IDs are not a unique, trusted server-minted identity

**Evidence:** reproduced basename collision; manifest handling inspected.  
**Location:** `src/migration_agent/adapters/mcp/binding.py:40`.

The fallback ID uses only a sanitized directory basename, so distinct roots such as `one/app` and `two/app` both produce `app`. A repository manifest can supply an arbitrary project ID, which is accepted at binding time without applying the identifier validation rules.

This does not itself permit changing the bound filesystem root. It is an inadequate identity for the planned shared trust records, project locks, and operation routing. IDs containing the prohibited `..` sequence can also be minted from a legitimate directory name and subsequently rejected by the same binding's tools.

**Remediation:** use a collision-resistant identity bound to the canonical repository and the out-of-band project registration. Validate candidate IDs at startup. Treat an in-repository ID as a claim to verify rather than as its own authority. Retain a separate friendly display name if useful.

**Acceptance tests:** equal basenames at different roots, invalid manifest IDs, names containing `..`, and duplicate manifest IDs must not cause ambiguous identities or an unusable bound server. Trust/lock routing must also verify repository binding.

### R08 — P2 contract gap: minimum identity and tool capabilities are implicit

**Evidence:** inspection.  
**Locations:** `src/migration_agent/adapters/mcp/server.py:65`, `src/migration_agent/adapters/mcp/tools.py:77`.  
**Plan reference:** endpoint policy table, reference plan lines 241–254.

The plan requires `run.read`, `plan.read`, and `changeset.read` with Mode B for the corresponding read tools. The server currently carries a project binding and settings, but no explicit actor/session assurance or server-side capability check. The only demonstrated authorization-like check is equality of a caller-supplied project ID.

Because the current transport is local stdio, this finding does **not** claim remote anonymous network access. If ownership of the launched local process is intended to establish Mode B, that mapping and its policy must be explicit and tested. A root binding is a scope restriction, not a capability policy.

**Remediation:** establish a typed trusted execution context at server startup and authorize each endpoint through the application policy layer. Determine Mode B from trusted process/session evidence rather than a model-provided flag. Keep ordinary doctor/inventory access consistent with their Mode C policy. Do not expose reusable credentials to the model.

**Acceptance tests:** allowed and denied capabilities; insufficient assurance; policy requiring stronger assurance; binding equality without permission. Resolve this contract before implementing mutation endpoints.

### R09 — P2: result payloads and preview work are unbounded

**Evidence:** inspection.  
**Locations:** `src/migration_agent/adapters/mcp/models.py:41`, `:66`, `:79`; `src/migration_agent/adapters/mcp/tools.py:61`, `:132`, `:188`.

Inventory returns its entire file list, plan show returns the full plan/evidence, and preview returns the complete generated diff. There is no response byte budget, paging, truncation marker, or artifact-reference contract. Preview also performs the full discovery/generation work before returning.

Large projects or oversized proposal content can therefore overrun practical client/context limits or tie up a tool call. This is an operability gap established from the absence of controls, not a claim that an actual host crashed during the review.

**Remediation:** define bounded typed response views with counts, digests, truncation metadata, pagination or bounded artifact reads. Do not truncate an executable ChangeSet silently. Carry expensive operations into the durable/cancelable lifecycle in 16B. Enforce file/input budgets before generation, not only after serialization.

**Acceptance tests:** large inventory, large plan evidence, and large diff; bounded outputs remain valid JSON and clearly identify omitted data; a host can retrieve the complete authorized artifact through the documented bounded route.

### R10 — P2: compatibility evidence and approval documentation are inaccurate

**Evidence:** document comparison; actual client capability claims were not independently verified.  
**Locations:** `docs/mcp-compatibility-spike.md:7`, `:18`, `:42`, `:58`, `:62`, `:75`, `:76`; `docs/phase-status.md:767`.

The spike states specific Antigravity/Codex protocol and human-input capabilities as conclusions, but contains no client version/build, executed procedure, observations, trace, official source references, or date-specific support evidence. The contract tests connect the Python SDK client and a synthetic JSON-RPC client, not the actual required hosts.

The same document describes approval as a legacy `ApprovalSignature` over the plan/policy, written to `.agent/plans/<plan_id>.json`. The final plan requires an exact-ChangeSet `ApplyApprovalRecord` stored out of source so approval does not dirty the base. It also names a future `migration-agent approve <step_id>` command without clearly distinguishing it from today's implemented CLI, assigns the wrong statement to master-plan invariant 10, and describes 16D as notification/audit work rather than setup/skills/documentation verification.

**Remediation:** separate observed, source-supported, and unverified host capabilities. Record versions, test procedure, outcomes, and the chosen approval channel for each primary client. Correct the approval entity, digest coverage, storage location, command availability, invariant reference, and milestone descriptions. Treat terminal-assisted approval as the conservative design choice pending measured host support, not as proof that every host lacks an authenticated channel.

**Acceptance tests/evidence:** measured 16A approval-boundary spike for both primary hosts; 16D end-to-end smoke checklists with actual versions and reproducible results. Documentation must match the accepted ChangeSet approval contract.

### R11 — P2: the subprocess test can hang and its redaction assertion is incomplete

**Evidence:** inspection.  
**Locations:** `tests/contract/test_mcp_server.py:420`, `:439`, `:458`, `:468`, `:478`.

Three blocking `stdout.readline()` calls have no request deadline. A startup failure or lost response can hang the test before it reaches `communicate(timeout=5)`. The test terminates the process explicitly, so it does not establish graceful disconnect/EOF handling.

The secret assertions inspect only the unconsumed stdout remainder and stderr, excluding the three response lines already read. They supply fake API keys to the environment but never intentionally emit a secret-bearing log or request source-derived preview data. A passing test therefore does not establish the stated protection of all MCP bytes.

**Remediation:** use a timeout-aware client/reader and drain both streams safely. Preserve and check the entire stdout transcript. Exercise a deliberate fake-token log plus plan/preview/error payloads. Verify normal EOF, startup failure, malformed request, and controlled cancellation independently.

**Acceptance tests:** every request is bounded; cleanup occurs on failures; any non-JSON stdout or fake token in any frame fails; expected disconnect exits cleanly without requiring forced termination.

## 4. Verification performed

All review probes used disposable projects and synthetic values. No real credential, live provider call, source migration, or actual client configuration write was required.

| Check | Result |
|---|---|
| `uv sync --all-groups --offline` | Passed; 69 packages resolved, 68 checked |
| `uv run --offline pytest tests/contract/test_mcp_server.py -q` | Passed; all nine MCP contract tests |
| `uv run --offline pytest -q` | Passed; full suite, two skips, no failures |
| Collection cross-check | 356 tests collected; with the two skips, 354 passed |
| `uv run --offline ruff check .` | Passed; repeated successfully after removing the temporary probe |
| `uv run --offline ruff format --check .` | Passed; repeated successfully after removing the temporary probe |
| `uv run --offline mypy src` | Passed; 82 source files |
| `uv run --offline migration-agent doctor` | Passed; status `ok`, Python 3.12.14, MCP 2.2.0, model configuration not required |

The `--offline` equivalents were used to avoid network-dependent verification. The initial Windows sandbox process launch failed with account restriction error 1327; checks then ran through the permitted execution path. This is an environment limitation, not an implementation finding.

### Reproduced behavior summary

| Probe | Actual outcome |
|---|---|
| Bound A, retrieve B plan from shared state | B plan returned |
| Bound A, retrieve B run from shared state | B run returned |
| Bound A, preview B plan | Preview generated against A and persisted |
| Different roots with the same directory basename | Same project ID minted for both |
| Request unknown step | Accepted; four generated files in the fixture |
| Fake token in plan description | Returned unchanged |
| Fake token in rendered template | Returned in diff and persisted in ChangeSet |
| State directory equal to source | Database created inside source |
| Preview helper without injected store, missing plan | Nested database created inside source before error |
| Synthetic transport exception | Masked by `NoEventLoopError` |
| External CSS via companion symlink | Read by extractor |
| External template via companion symlink | External marker returned in preview diff |

A minimal reproduction pattern for R01 is:

```python
# Create two disposable roots A and B and one shared SqliteCheckpointStore.
# Save a MigrationPlan and RunRecord whose source_root points to B.
binding = ProjectBinding(A)
handle_plan_show(binding, binding.project_id, plan_b.plan_id, store)
handle_run_status(binding, binding.project_id, run_b.run_id, store)
handle_step_preview(binding, binding.project_id, plan_b.plan_id, step_b.step_id, store)
# Current behavior: all succeed; expected behavior: project mismatch rejection.
```

For R03, copy `tests/fixtures/ember-classic-mini` into a disposable directory, replace its user-card template with a symlink to an outside HTML fixture, and call preview for the valid user-card step. A synthetic template such as `<div ng-if="true">outside-template-review</div>` currently places that marker in the returned diff.

**Verification limits:** review probes called the handlers directly; transport serialization was inspected and the existing protocol tests passed. Actual Antigravity/Codex sessions, Linux execution, real signing channels, and absent 16B–16D behavior were not tested. No claim of verified host compatibility or completed approval security follows from this review.

## 5. What is implemented well

- The official MCP SDK is reused instead of adding a custom JSON-RPC parser.
- The new result models are typed, forbid extra fields, and carry relevant IDs/digests.
- MCP-specific registration and transport behavior live in adapters; doctor extraction removes the CLI import dependency from the server route.
- Normal protocol initialization, tool discovery, schemas, inventory, plan display, preview, and doctor work in offline tests.
- The server does not expose a model-callable approval or source-apply tool at this milestone.
- The work is limited to a small foundation rather than speculative GUI infrastructure.

These strengths should be retained while fixing the actual boundary checks. Passing static checks and happy-path contracts does not replace project ownership, actual-read containment, or disclosure tests.

## 6. Suggested remediation order and gates

### Package A — Restore the 16A source and data boundaries

1. **R01:** project ownership for every retrieved and related record.
2. **R02:** root separation before state writers; eliminate the source-local fallback.
3. **R03:** guarded reads for discovery, companion files, fingerprinting, manifest, and plan fallback.
4. **R04:** response protection and secret-bearing artifact rejection before persistence.

**Gate:** focused adversarial tests prove no foreign-project content, outside-root bytes, source-state writes, or synthetic-token disclosure/persistence through the affected paths.

### Package B — Complete the 16A correctness and contract gate

5. **R05–R06:** enforce step membership/scope and repair shutdown/error handling.
6. **R07–R09:** define trustworthy project identity, trusted local session policy, and bounded result contracts.
7. **R10–R11:** correct the spike and add measured host evidence; strengthen subprocess, redaction, and disconnect tests.
8. Update the phase status to reflect verified evidence; run all six required repository commands after remediation.

**Gate:** negative-path contracts and required quality gates pass; the 16A human-approval compatibility spike has actual observations for Antigravity and Codex.

### Package C — Execute the outstanding accepted plan

9. **16B:** typed host proposals, bounded evidence reads, durable/idempotent operations, cancel/status, lock/lease fencing, and lifecycle/recovery enforcement.
10. **16C:** exact-ChangeSet headless human approval and the shared, non-bypassable apply gate; run the six mandatory security scenarios in the reference plan.
11. **16D:** setup generation, host instruction packs, actual Antigravity/Codex/standalone smoke flows, and synchronized documentation.

**Gate:** the complete headless journey is reproducible in all three required modes. Existing GUI files are not a substitute for this evidence and need no new Phase 16 implementation.

## 7. Original review disposition (before remediation)

**Phase 16 overall:** incomplete.  
**Phase 16A:** normal functionality passes, but acceptance should remain pending remediation of the reproduced boundary defects and missing compatibility evidence.  
**Changes made during this review:** this report only; temporary fixture probes were used for verification, with no implementation fixes.

## 8. Current disposition after authorized remediation

This section records the earlier 16A-only remediation. For the subsequent
authorized 16B–16D implementation and remaining acceptance evidence, see
[Phase 16 remaining implementation report](phase-16-remaining-implementation-report.md).

**Phase 16A code remediation:** complete. **Phase 16A actual host compatibility acceptance:** pending. **Phase 16 overall:** incomplete; 16B–16D remain separate outstanding milestones.

| Finding | Completed correction / remaining evidence |
|---|---|
| R01 | Every plan/run read verifies canonical source ownership, record identity, and related plan/run associations. Preview uses the bound plan. |
| R02 | Source/state/staging root equality and ancestry overlap are rejected before state writers. Preview requires an injected store; the source-local fallback is removed. |
| R03 | Actual script/template/style/manifest/plan reads enforce path containment and reject links/reparse points, ignored paths, credential filenames/content, and oversized inputs. Fingerprints enforce bounded safe reads and explicit path checks. |
| R04 | Display DTOs and SDK text/structured responses redact recognized credential patterns. Input/validation errors are protected. Credential-bearing source or generated artifacts are rejected before ChangeSet persistence. |
| R05 | Missing, unknown, blank, or duplicate step selections fail closed. A sole omitted step is selected explicitly. Expected component/service paths constrain generation; discovered component identity is preserved and duplicate outputs are rejected. |
| R06 | Startup, transport failure, synchronous interrupt, and asynchronous cancellation have defined handling that preserves stderr/stdout separation. |
| R07 | Project IDs include a canonical-root hash; validated manifest claims cannot determine authoritative identity. |
| R08 | Typed local inspection context enforces capability and assurance policy. Tool arguments cannot supply trusted actors/grants or authorize apply. |
| R09 | Inventory/plan paging, aggregate read/fingerprint budgets, preview limits before persistence, and input/DTO/protocol byte caps are enforced. |
| R10 | Unsupported IDE compatibility claims withdrawn; approval notes refer to exact-ChangeSet `ApplyApprovalRecord` and separate future milestones. **Real Antigravity/Codex spike measurements remain pending.** |
| R11 | Subprocess tests use request deadlines, concurrent stream draining, full-transcript validation/redaction checks, and clean stdin EOF. Negative-path SDK and startup contracts were added. |
| C01 | **16B–16D remain outstanding.** No proposal, durable operation, signing/apply, setup, or later GUI infrastructure was added. |

Related defects exposed by the regression suite were also corrected: standalone plan creation records the actual inspected repository as `source_root` when exports use a separate directory, and SQLite transactions close their connections to avoid lingering Windows handles.

### Final verification

| Required command | Result |
|---|---|
| `uv sync --all-groups` | Passed; resolved 69 packages, checked 68 |
| `uv run pytest` | Passed; **402 passed, 2 skipped in 39.37s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 189 files already formatted |
| `uv run mypy src` | Passed; 83 source files |
| `uv run migration-agent doctor` | Passed; status `ok`, Python 3.12.14, MCP 2.2.0; model configuration not required |

Regression coverage is in `tests/unit/test_mcp_read_safety.py`, `tests/contract/test_mcp_server.py`, and the planning service tests. Verification ran on Windows with local fixtures and synthetic credential values. Linux execution and actual Antigravity/Codex sessions remain unverified. Automated MCP clients establish SDK behavior only.

### Compatibility and next gate

- Obtain current opaque project IDs from the server; basename/manifest-derived IDs are no longer authoritative.
- Regenerate and approve older plans that incorrectly stored an export directory as `source_root`; signed plan identity is not silently rewritten.
- Use paging for inventory/plan collections and handle limit errors explicitly. Display-only plan pages/redacted views are not executable approval artifacts.
- Complete the measured host spike described in `docs/mcp-compatibility-spike.md` before closing the remaining 16A compatibility acceptance gate. Then proceed with 16B, 16C, and 16D under their own phase boundaries and required checks.
