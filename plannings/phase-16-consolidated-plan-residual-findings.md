# Residual findings in the consolidated Phase 16 plan

Reviewed: 2026-10-04  
Source: `C:\Users\vkumar\.gemini\antigravity\brain\7a712a9d-3abf-40c9-b956-2a25f5e24a5f\implementation_plan.md`  
Purpose: Small set of remaining corrections before implementation. The consolidated plan now covers the required Antigravity, Codex and standalone workflows and keeps the full GUI in its separate phase.

## Latest revision check

The subsequent revision of the source plan addresses all six findings below **in its design**. The earlier line references and findings are retained as review history; they are not current unresolved objections.

| Finding | Resolution in the latest source plan |
|---|---|
| 1. Repository-local trust root | Lines 97–100 anchor verification to the out-of-band trust store and enforce policy-specific assurance. |
| 2. Approval export dirties source | Lines 143–146 keep approvals outside the repository through apply and defer optional governance export. |
| 3. One-time lease check | Lines 178–206 add a continuously held exclusive OS file lock and checks before writes. |
| 4. Open-ended SDK dependency | Lines 314–315 and 388 specify a bounded dependency, locked version and protocol revisions. |
| 5. Assumed host approval | Lines 316–320 and 392 make host approval a compatibility spike with an explicit terminal-assisted fallback. |
| 6. Incorrect state/drift path | Lines 277–308 define twelve states and route drift through re-inspection/re-planning with artifact invalidation. |

**Recommendation:** Begin Phase 16A. Implementation and quality-gate evidence remain pending. Align its protocol-test exit criteria (line 399) with all revisions claimed at line 315, including `2026-07-28`; currently the exit criterion lists only the older revisions. Record the tested versions and host approval results before later milestones rely on them. This is a bounded Phase 16A contract correction, not a reason for another architecture redesign.

## P0 — Resolve before guarded apply

### 1. Keep Mode A trust roots outside the repository

**Plan evidence:** Line 97 verifies Mode A signatures against `.agent/config/trusted_signers.json`. The [master plan](final/agent-platform-master-plan.md) requires initial Authority Key trust to be bootstrapped out of band in `~/.agent-platform/trust/<project-id>.json`, bound to repository identity (invariant 24). A key list in the repository cannot by itself decide which repository key is trusted; otherwise a modified repository can nominate its own signer.

**Correction:** Use the existing out-of-band trust store as the root of authority. Repository files may contain candidate/public key metadata, but verification must anchor to locally trusted fingerprints, repository binding, revocation and capability policy. Specify whether an apply requires Mode A or Mode B under the existing policy; do not encode a blanket Mode B permission in the MCP table if production apply requires Mode A.

**Proof:** Replacing `.agent/config/trusted_signers.json` with an attacker key does not authorize apply; revoked and repository-mismatched keys fail through CLI and MCP.

### 2. Approval export cannot dirty the base just before apply

**Plan evidence:** Lines 75 and 393 persist `ApplyApprovalRecord` in SQLite **and export it to `.agent/approvals/<step_id>.json`** before `step_apply`. Lines 52, 159–160 and 394 require a fully clean working tree and exact base fingerprint at apply. A new or modified approval file inside the target Git repository can make that tree dirty and invalidate the ChangeSet approved moments earlier.

**Correction:** Keep operational approval records in SQLite/out-of-band state through apply. If a Git-versioned approval artifact is needed, specify a separately governed export after controlled apply or a pre-planned governance ChangeSet with its own base/approval treatment. Do not silently exclude `.agent/approvals` from drift detection. Test both tracked and untracked `.agent/` layouts.

**Proof:** Creating an approval does not change the source worktree fingerprint or cause `BASE_CHANGED`; a real source/governance edit still does.

### 3. A lease check once before patching does not fence a multi-file apply

**Plan evidence:** Lines 180–192 acquire a 60-second lease, check generation once, then create backups and apply patch chunks. If that process pauses after the check, its lease can expire and a second writer can acquire the next generation while the first resumes and writes. Line 198 therefore overclaims that duplicate patching is “mathematically impossible.” The diagram also calls a multi-file patch “atomic” (lines 53 and 277), which the transaction-like controlled apply protocol does not promise.

**Correction:** Hold a cross-process exclusive apply lock for the entire filesystem critical section, or use a design that demonstrably prevents stale writers from resuming each individual write. Keep the SQLite lease for durable ownership/recovery, but do not rely on a one-time generation check as a filesystem fence. Model apply as transaction-like with backups, postcondition checks and explicit recovery; remove “atomic patch” and absolute impossibility claims.

**Proof:** Suspend writer A after its generation check, let its lease expire, start writer B, then resume A. No concurrent source writes occur; the final disk state is verified or marked `RECOVERY_REQUIRED`.

## P1 — Resolve before Phase 16 completion

### 4. Pin the actual tested MCP SDK/protocol combination

**Plan evidence:** Lines 293 and 362 call `mcp>=1.2.0` a “pin.” It is an open lower bound, so it does not select a reproducible SDK release or a protocol era. The repository lock currently contains a later MCP release, while the plan promises both modern host compatibility and headless long operations.

**Correction:** Record one tested Python MCP SDK version in the lockfile and the exact protocol revisions served. Use a bounded dependency range consistent with that lock and test Antigravity/Codex against the selected combination. Avoid coding against a feature merely because some later SDK version might be installed.

**Proof:** A clean offline `uv sync --all-groups` installs the recorded version, and transport contract tests exercise the protocol used by the required hosts.

### 5. Make host-only approval support an explicit compatibility gate

**Plan evidence:** Lines 143–145 make terminal approval the primary path and host-mediated human confirmation optional; lines 299–300 and 418 call Antigravity and Codex required integrations. The earlier usability requirement was to approve from the IDE when a verified human-only host channel exists. The plan does not yet identify such a capability for either required host, nor a concrete fallback UX that stays in the IDE.

**Correction:** In the 16A compatibility spike, verify each required host's human-only approval mechanism and document the evidence. If either host lacks it, document the CLI review fallback honestly and do not claim complete in-IDE approval for that host. Keep approval out of model-callable tools in either case.

**Proof:** The client matrix records for Antigravity and Codex whether approval is in-IDE or terminal-assisted, with a reproducible human-only boundary test.

### 6. Correct the state table and drift recovery transition

**Plan evidence:** Lines 263 and 386 call the transition lifecycle “10-state” but list twelve named states. Line 283 allows `BASE_CHANGED --> STAGE_VERIFIED` after the Git tree is “restored / re-staged.” The [master plan](final/agent-platform-master-plan.md) says drift invalidates approval, staged output and validation and requires re-inspection/re-planning (invariant 25); simply returning to staged state can reuse stale artifacts.

**Correction:** Name/count the actual states consistently. Replace the direct `BASE_CHANGED --> STAGE_VERIFIED` edge with a verified re-inspection and fresh plan/ChangeSet/validation path. Reusing any old artifact requires proof it still matches the exact base and active policy; otherwise regenerate it and obtain a new approval.

**Proof:** A drifted run cannot resume staging, validation or apply by restoring Git cleanliness alone; stale approval and validation are invalidated.

