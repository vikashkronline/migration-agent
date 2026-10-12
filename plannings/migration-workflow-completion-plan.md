# Migration workflow completion amendment

Authorized by the user's 2026-10-12 instruction to address the workflow audit findings.
This is one bounded amendment to the master plan: complete the existing local,
capability-governed migration workflow. It does not introduce a hosted identity
service, provider OAuth, a remote daemon, or autonomous signing/deployment.

## Required behavior and implementation order

1. **Destination-bound execution (W01).** Keep source identity/evidence immutable.
   Carry a typed destination root and base fingerprint in each new ChangeSet,
   checkpoint and exact review. Stage from the cumulative destination, publish
   only approved bytes there, and verify destination drift, source drift and
   interruption recovery. Bind destination identity into approval and validation
   evidence. Reject overlapping roots and changing destinations for existing work.
   Reuse the existing durable workflow, approval, access fence and apply lock.
2. **Foundation contract (W03).** Align generated lint/test setup and smoke checks
   with fixed catalog commands. The approved preset owns generated configuration;
   no owner-authored target patch is needed to pass the base checks.
3. **Architecture and scope (W04/W05).** Require verified cumulative foundation
   evidence before functional work in separate-target sessions; require exact
   source-bundle selection and stable qualified output identities. Remove the
   independent hardcoded dependency rewrite from the functional renderer.
4. **Faithful supported conversion (W02).** Preserve supported Ember templates,
   styling and method semantics; reject unsupported constructs with source-bound
   diagnostics instead of substituting generic cards or empty methods. Keep
   framework parsing/rendering in adapters. Unknown application semantics remain
   an explicit task requiring a supported transformation, never a fabricated pass.
5. **Team continuity (W06/W07).** Preserve Mode B's local-account boundary and
   provide explicit Mode A guidance for independent role handoffs. Make identity,
   onboarding, prerequisites and Git enforcement responsibilities discoverable.
   Provide public onboarding information without exporting secrets or implicitly
   trusting copied anchors. Remote Git authority remains independently configured.
6. **GUI continuity.** Select actual eligible foundation plan/step records instead
   of typing IDs; eliminate fixed task labels; align directory-fetch deadlines and
   diagnostics; expose target identity and real prerequisite guidance.
7. **Acceptance and documentation.** Exercise the product workflow on disposable
   supported fixtures, including cumulative tasks, distinct-role signature checks,
   drift/recovery and unchanged source. Reconcile stale operations guides. Record
   remaining real-application/deployment prerequisites without claiming success.

## Architectural decisions

- Destination metadata is additive and digest-bound. Historical in-place records
  remain historical; they cannot be reinterpreted as destination-bound approvals.
- Root selection is not permission. Every apply still requires current RBAC,
  exact approval, passing execution evidence and policy-required assurance.
- Destination snapshots are not model-generated shell input. Existing guarded
  file operations publish typed ChangeSets and verify safe roots at every boundary.
- Cumulative target state advances through guarded apply; a prerequisite's staged
  files are never silently overlaid or treated as approved target content.
- Concurrent publication to the same destination must share an apply lock even
  when operational state roots differ. Recovery verifies the bound destination.
- Accepted architecture is the source of generated package/configuration choices.
- Local GUI sessions continue to represent the launcher's OS principal. A Git
  import is pending enrollment, not authentication or trust bootstrap.
- Fail-closed diagnostics are necessary for unsupported constructs; they are not
  proof that the supplied application has been fully converted.

## Quality gates

Focused regressions for each introduced behavior, then `uv sync --all-groups`,
`uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy src`, `uv run migration-agent doctor`; GUI unit/lint/format/build and
real browser acceptance where installed tooling permits it. No test requires
network credentials. Update phase status, operations and the audit disposition.

## Execution record

- Started: reviewed master plan, current phase status and W01-W07 audit. Existing
  workspace changes are retained. No selected source or generated target file has
  been manually edited.
- Implemented destination-bound cumulative execution, exact Ember scope/semantics,
  grounded initial generation, preset-aligned foundation checks, signed architecture,
  independent-role handoffs, onboarding, configuration freshness and GUI continuity.
- Verification and documentation reconciliation are underway; see the
  [implementation report](migration-workflow-completion-implementation-report.md).
