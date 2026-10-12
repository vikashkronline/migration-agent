# Migration workflow and team readiness audit

Date: 2026-10-12. Scope: current platform implementation, owner/developer/reviewer workflow, and the requested separate-governance migration with a strictly read-only Ember source.

## Implementation follow-up

The subsequent user instruction authorized a bounded completion amendment.
The [implementation report](migration-workflow-completion-implementation-report.md)
records changes and verification for W01–W07. The original findings below remain
historical evidence; they are not the current capability description. Use the
[current workflow guide](../docs/migration-workflow.md) for operational steps and
the remaining owner/deployment and business acceptance boundaries.

## Verdict

**The workflow is not yet complete for a successful end-to-end migration under these requirements.** RBAC, configuration, durable operations, staging, validation evidence, review and recovery have substantial implementations. They do not establish a complete application converter, a cumulative target workspace, separate-target publication, or frictionless distributed team operation.

The current product supports a supervised local workflow across GUI, CLI and IDE/MCP. It is not an all-GUI migration service or a Git-provider-authenticated multi-user portal. Several terminal handoffs are intentional security boundaries. Other gaps below are implementation defects or missing workflow contracts.

This is a code/documentation audit. No migration was executed, no selected source was changed, and no target code was generated or edited. Findings distinguish direct code evidence from missing acceptance evidence. No implementation phase is authorized by this report.

## What each surface currently handles

| Workflow stage | GUI | CLI / authorized IDE host | Core responsibility |
| --- | --- | --- | --- |
| Separate project initialization | Inspect an already bound project; no complete first-run enrollment wizard | `agent init GOVERNANCE --source SOURCE --state-dir STATE --staging-root STAGING`; commit governance deliberately; bootstrap owner externally | Reject unsafe root overlaps and bind project identities |
| Owner enrollment / trust | Not an independent trust-bootstrap channel | `access identity`, bootstrap, review and exact interactive signing; administer external trust permissions | Verify owner authority, active signed revision and repository binding |
| Users and roles | Discover connected Git repository; import existing members; prepare role/status/ownership changes and inspect proposals | Bind OS identities, enroll public keys and possession proofs, sign exact governance changes | Finite capabilities, client ceilings, expiry, revocation and last-owner protection |
| Configuration | Settings: effective values, models, directories, environment, validation, workflow, governance/history; eligible personal saves and shared proposals | Securely provision credentials outside the product; approve shared revisions; restart with supported root/configuration handoffs | Resolve constraints/provenance, protect shared configuration and bind operation snapshots |
| Architecture / foundation | Detect/recommend stack, edit supported mappings, generate ADRs, eligible human confirmation; stage a recorded foundation step | Produce grounded analysis and a saved foundation plan through approved provider/host; supply actual plan/step IDs | Require accepted current foundation decisions and use the guarded durable staging service |
| Functional analysis / planning | Inspect existing plans, tasks, dependencies and knowledge; recorded-facts Ask | Provider CLI or IDE/MCP submits grounded analysis, plan and repair proposals | Validate evidence, base, scope, supported transformations and dependency DAG |
| Generation / staging | Stage a selected recorded step where authorized; show results/diffs | Same shared stage service; host submits bounded repair proposals | Deterministically render supported constructs into external staging |
| Validation | Trigger selected-task validation; inspect checks, diagnostics, screenshots and readiness | Provision toolchain/dependencies/browser plan; human native execution consent; browser AI review/submission and repair | Fixed commands, bounded execution, immutable evidence, freshness and policy checks |
| Review / approval | Read-only changed-file diff and exact approval handoff | Reviewer inspects and approves in a trusted interactive terminal; full repository review remains IDE/CLI | Bind approval to exact bytes, base, policy, validation, principal, expiry and nonce |
| Apply / recovery | Explicit guarded apply where authorized; inspect recovery state | Same guarded apply; explicit recovery and human follow-up | Locks/fences, backups, single-use approval, rollback and postconditions; currently writes to selected source |
| Git / delivery | No automatic remote protection, commit, PR, merge or deployment workflow | Trusted Git administration, verifier installation, commits/PRs and release procedures | Governance publication verifier checks immutable signed Git content; it is not target application publication |

The core is used by all entry points. It is not an additional interface that users must operate. GUI and MCP cannot manufacture missing authority, execution consent or approval.

## Role workflow and its practical limits

| Role | Can normally do | Requires another authority or separate preparation |
| --- | --- | --- |
| Owner | Configure shared policy, manage users/roles, approve architecture and perform registered project operations | Trusted bootstrap, secure signer, dependency/toolchain provisioning, Git-server enforcement and business acceptance preparation |
| Administrator | Whatever finite capabilities the owner assigns through a custom role | There is no built-in role named `admin`; role names alone confer no authority. Owner-list and key constraints still govern ownership |
| Developer | Read, submit analysis/plans/repairs, stage, run validation, request review; propose shared configuration and save eligible personal settings | Default developer cannot grant native execution consent, sign workflow approval or apply. Native work needs an authorized operator/owner and a compatible assurance arrangement |
| Reviewer | Inspect, request review, sign exact workflow approval and approve knowledge | Needs active managed identity and signing-key enrollment for Mode A; cannot ordinarily stage, execute validation or apply |
| Operator | Developer capabilities plus native execution consent and apply | Still needs valid exact review approval and matching current execution evidence |

Existing signed policies retain their explicit capabilities; installing newer code does not silently add configuration permissions to old roles.

**Important cross-role limitation:** Mode B is account-local. `AccessApprovalAuthority.accepts()` requires the approving/consenting member's OS identity to equal the current execution identity, and `LocalApprovalProof.verify()` checks the current OS username. Consequently, a different developer cannot consume an operator's Mode B native consent, and a different operator cannot consume a reviewer's Mode B approval. Team separation needs appropriately enrolled Mode A signers and a trusted shared operating arrangement, or a separately designed delegated-consent contract. Sharing one owner's OS account/session is not a valid solution for independent RBAC.

The loopback GUI authenticates access to the process launched under a managed OS identity. A browser session is not a separate Git-user login. Importing a Git member creates a pending agent member; it does not give that person a working authenticated GUI session. Different machines/clones require trusted identity/root provisioning; path-bound trust and local SQLite history do not become portable by pushing governance Git files.

## Blocking findings

### W01 — Critical: separate-target completion and cumulative execution are unavailable

Evidence: `adapters/workflow_runtime.py:95`, `adapters/controlled_files.py:35,128`, `application/apply.py:319`, `docs/project-configuration.md:22`.

The runtime constructs `LocalControlledFiles` with the selected project/source root. Its apply mutations target that root. The configured final target directory is explicitly planning-only. Separate initialization itself even states that source apply is outside the read-only session's scope.

Each stage starts from a fresh copy of the source and overlays the current ChangeSet. It does not automatically compose the previously validated foundation and functional changes into a persistent separate target. Dependent validation requires prerequisites to be `APPLY_COMPLETED`, so validating foundation alone cannot unlock a complete dependent validation chain without the current source apply path.

Impact: the requested source-preserving Ember-to-Angular workflow cannot reach approved final delivery. Copying staged files manually would bypass the requested product workflow. A source clone would change the requested execution model and would not supply missing separate-target semantics.

Required completion: distinct immutable source and mutable target identities; a cumulative target base/checkpoint; destination-bound staging, validation, approval, locks and recovery; explicit approved publication to the target; source byte/cleanliness verification throughout.

### W02 — Critical: Ember output does not preserve application behavior

Evidence: `adapters/transforms.py:94,592,661,703,746`, `adapters/frameworks.py`, `application/host_proposals.py:226`.

Current discovery includes classic, feature and pod components. The earlier start guide's assertion of zero supported pod discoveries is therefore stale and must not be used as current evidence.

However, extraction records method names rather than their full semantics. Rendering supplies heuristic toggle bodies and empty bodies for other methods. For ordinary Ember templates, the renderer generates a generic Details card rather than translating the Handlebars template; styles are replaced with a small generic stylesheet. This can produce syntactically plausible output while losing visible controls, business actions and layout.

The Ember adapter exposes a component extractor but no Ember service extractor. The shared host plan boundary accepts only component, service and foundation scopes; complete route/controller/helper/model/mixin/authentication/data-contract migration is not implemented by that boundary.

Impact: file generation or a passing build cannot establish a faithful migration. Unsupported semantics must be rejected explicitly rather than silently replaced with scaffolding. Supported transformations need preservation contracts and business parity tests before this application can be declared migratable.

### W03 — High: generated foundation and actual validation disagree

Evidence: `adapters/foundation_transformation.py:125,130,331`, `adapters/fenced_validation.py:26`, `domain/stack_catalog.py`.

The foundation emits `test: vitest run`, no lint script, no lint configuration and no test setup/configuration. The shared validator calls `npm run lint` and invokes tests with `--watch=false --browsers=ChromeHeadless`, which is a Karma-style contract inconsistent with that Vitest foundation. Component specs also assume Jasmine-style globals/matchers.

Impact: the generated base cannot satisfy the documented full check set as emitted. The lint mismatch is direct; the test integration needs a real installed-preset run to establish the precise failure sequence. These are platform generator/catalog defects, not requests for the owner to hand-edit target files.

Required completion: an installed preset with consistent generated lint/test configuration, deterministic runner-specific allowlisted commands, an appropriate initial smoke test, and a real staged lint/typecheck/test/build/browser acceptance run.

### W04 — High: foundation/ADR precedence is not universal

Evidence: `application/host_proposals.py:209`, `application/validator.py`, `application/apply.py:242`, `application/transformation.py:375`.

Plan validation checks declared dependencies and cycles but does not require every applicable functional task to reference an accepted, validated foundation. The recent foundation staging gate only examines explicit dependencies in the same plan. Omitted edges or foundation evidence in another plan are not covered by that gate.

Additionally, the functional transformation path contains a separate package rewrite triggered by expected `package.json`, hardcoding Angular 18 dependencies and `ng test` independently of the accepted Angular 17 foundation preset. A component/service plan including that file can reach the branch; the dedicated dependency scope itself is rejected by the shared host plan boundary.

Impact: accepted architecture is not the sole source of target configuration, and topological safety depends on plan authors supplying all required edges. Foundation state should be a verified project/target prerequisite; every transformation must derive configuration from the accepted architecture contract.

### W05 — High: pod task selection can exceed intended scope

Evidence: `application/transformation.py:240,254,283`.

Component selection compares basename substrings as well as source paths. Many pods share `component.js` and `template.hbs`; an expected pod path containing those basenames can match unrelated bundles. Output identity uses the final component-directory name rather than its full feature namespace, allowing similarly named feature components to collide.

Impact: a small reviewed task can generate unrelated components or fail with path collisions. Selection should use exact normalized bundle membership and stable source-qualified component identities. Validate emitted paths against the declared task contract.

### W06 — High for team use: onboarding and independent role handoffs are incomplete

Evidence: `adapters/access_runtime.py:72`, `adapters/access_approval_authority.py:42`, `adapters/approval_proof.py`, `docs/rbac-and-users.md`.

Git import, OS binding, public-key proof, owner activation, external trust provisioning and local runtime setup are separate steps. There is no provider OAuth identity login, centralized multi-user GUI or demonstrated cross-machine state/artifact transfer. The `transferable` status flag indicates a quiescent lifecycle; it does not implement secure cross-host export/import or trust rebinding.

Mode B cross-role constraints described above can block developer validation and reviewer-to-operator approval consumption. Establish and test a supported managed-host deployment model and Mode A team handoffs before presenting the workflow as frictionless team collaboration.

### W07 — High for protected governance: Git-server enforcement remains external

Evidence: `docs/rbac-and-users.md:215` and publication/gate-status operations.

Agent RBAC prevents unauthorized effective policy/rule/configuration changes inside agent operations. It does not stop a user with Git permission from pushing candidate files to a feature branch. Authoritative promotion requires independently trusted server/CI verification, protected branches, force-push restrictions and constrained bypass permissions. `gate-status` reports remote enforcement unverified; no live remote protection or rejected unauthorized push has been established by the implementation tests.

Git removal also does not automatically revoke agent membership. Owner-signed suspension/removal remains a manual offboarding requirement.

## Avoidable friction and remaining acceptance risk

- **Git directory timeout mismatch:** individual provider requests can aggregate to roughly four minutes while the GUI response timeout is fifteen seconds. The read-only operation continues after the GUI times out. Use a bounded background operation with status/cancellation and an overall deadline.
- **Foundation handoff:** the wizard requires manually entered plan/step IDs and still labels the stage button with a fixed `step-001`. Select real eligible recorded steps and preserve context in the handoff; avoid an implied automatic plan generator.
- **Environment provisioning:** the product configures/checks installed tools but does not install dependencies, generate an approved dependency cache or download browsers. The foundation output does not generate a lockfile. Provide a documented trusted provisioning contract; package presence/hashes alone do not prove preset/dependency compatibility.
- **Business acceptance:** browser visual checks do not prove API, authorization, persistence, localization or calculations. Actual routes/states, synthetic fixtures and mandatory business journeys must be specified and run. Disabled E2E is `NOT_RUN`.
- **Capacity fit:** current native limits include a 60-second command deadline and Windows 512 MiB aggregate process memory. Measure real target builds/tests against these limits; do not assume small fixture success establishes production viability.
- **Documentation drift:** the initial migration start guide has obsolete pod-discovery claims and a source-writing apply example. Older phase entries also describe superseded GUI permissions/readiness. Publish one current entry workflow identifying deliberate handoffs and read-only session limits.
- **Terminal switching:** exact approval, governance signing and native consent are intentional boundaries, not inherently defects. Improve contextual handoffs and return-to-task reconciliation without replacing a required signature with a session token.
- **Operational completion:** automatic commits/PRs/releases are not necessary for a local guarded migration, but the workflow must document who owns final integration, rollback, parity sign-off and delivery. These have not been exercised for the supplied application.

## What the owner must prepare manually

1. Choose separate governance, source, staging, state and trust roots. Commit source/governance bases and protect the original source. Use a new project/session rather than reusing old initialization.
2. Provide the governance Git repository and independently configure its authoritative branch protections and trusted verifier. Verify an unauthorized candidate cannot be promoted; use server hooks if literal push rejection is required.
3. Establish managed OS identities, trust-directory permissions and owner-controlled signing keys. Import Git accounts, explicitly assign agent roles, bind identities, obtain public-key possession proofs and activate signed memberships. Decide how operators/reviewers will perform Mode A handoffs.
4. Define migration objectives, target architecture, dependency decisions, deployment/API contracts, business behavior and acceptance criteria. Approve supported ADR proposals; resolve custom mappings instead of pretending they are transformed.
5. Provision approved provider credentials through the SDK/host's secure mechanism when provider reasoning is used. Configure only non-secret provider/model identifiers and authorized disclosure purposes through Settings.
6. Provision an appropriate installed toolchain, approved offline dependencies and browser, or a supported pinned container image. Provide route/state coverage, synthetic backend fixtures and business journeys. Configuration checks are not migration validation.
7. Agree task ownership, review/apply responsibilities, source revision changes, recovery procedures and offboarding. Select an explicitly supported local deployment arrangement until team handoff is completed.

These preparations must not include manually writing Angular components, package/configuration files or repairing generated target code. Defects in those outputs belong in the agent implementation, followed by regeneration through the product.

## What to share with a developer

Supply a public onboarding packet containing:

- Governance repository URL, approved revision, logical project ID, source repository URL and exact read-only base commit; target architecture/ADRs and intended delivery contract.
- Assigned agent principal/roles/capabilities, enrollment instructions, public-key proof workflow and the responsible owner/operator/reviewer. Git role membership alone is insufficient.
- Agent installation/version, supported host setup instructions and non-secret launcher configuration; each managed environment's authorized source/state/staging/trust paths and provisioning instructions.
- Approved toolchain/dependency identities, browser plan, synthetic fixtures, required profiles, disclosure policy and recovery documentation.
- Actual saved analysis/plan/step IDs, dependencies, acceptance criteria and access to the authoritative operation/artifact store for the agreed deployment.
- A first-task checklist: verify identity/capabilities, effective configuration and base; confirm prerequisites; stage; obtain applicable execution consent; validate and inspect evidence; request reviewer approval; operator performs approved publication once separate-target support exists.

Do not share owner private keys, SSH-agent sockets, browser session credentials or unreviewed copies of trust/state as a substitute for enrollment. Sharing Git files alone does not establish a trusted runtime or transfer operational history.

## Evidence and completion criteria

The latest implementation report records 773 Python tests passed, 3 platform-specific skips, 19 focused follow-up tests, 37 UI tests, lint/format/type checks, build and real loopback Settings browser acceptance. These are valuable platform/fixture results. They do not prove a complete migration of the supplied application, independent team handoffs, enforced remote Git protections or separate target publication. This audit did not rerun those suites or claim new execution acceptance.

A focused in-memory check of the actual `AccessApprovalAuthority.accepts()` predicate confirmed that a Mode B reviewer record is rejected for a different OS identity and accepted for the same identity. This verifies the role-handoff restriction; it is not enrollment, signature verification or real team acceptance evidence. The report was inspected after writing; no runtime/application files were edited.

Before marking end-to-end complete, demonstrate through the product:

1. A fresh separate project, trusted owner bootstrap, active developer/reviewer/operator enrollment and a tested protected governance branch.
2. Agent-generated foundation passing real installed-preset checks and browser evidence without manual target edits.
3. One complete vertical feature: routes, template interactions, services/API contracts and business behavior; unsupported constructs fail explicitly.
4. Declared and mandatory prerequisites enforced across the cumulative target, with architecture precedence respected by every transformation.
5. Distinct developer generation/validation, reviewer approval and operator publication using genuine eligible identities and the required assurance.
6. Destination-bound delivery, resume, drift, revocation and interrupted-publication recovery with the original source unchanged.
7. Expansion to all required application scope and passing agreed business journeys, followed by a documented owner acceptance/integration decision.

Recommended implementation order: separate target/cumulative workflow and its trust bindings; consistent foundation validation; faithful transformations with exact scope and architecture enforcement; managed team onboarding/handoffs; then GUI continuity, documentation and real application/team acceptance. This ordering is a proposed next scope, not authorization to implement it.

## Primary repository references

- [Master architecture](final/agent-platform-master-plan.md)
- [Current phase status](../docs/phase-status.md)
- [Control Center boundaries](../docs/control-center.md)
- [RBAC and users](../docs/rbac-and-users.md)
- [Configuration operations](../docs/project-configuration.md)
- [Shared host workflow](../docs/phase-16-host-workflow.md)
- [Client setup and handoffs](../docs/phase-16-client-setup.md)
- [Native validation](../docs/native-validation.md)
- [Browser review and business evidence](../docs/browser-ui-ux-validation.md)
- [Configuration implementation evidence](agent-configuration-management-implementation-report.md)
