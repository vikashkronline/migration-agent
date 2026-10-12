# Migration workflow completion implementation report

Date: 2026-10-12. Authorization: implement the workflow audit gaps within the
existing local architecture. This report accompanies
`migration-workflow-completion-plan.md`; it does not authorize a hosted identity
service, distributed state system or later speculative infrastructure.

## Implemented behavior and audit disposition

| Finding | Implemented change | Practical boundary |
| --- | --- | --- |
| W01 Separate target | Typed destination root/base in artifacts, checkpoints, consent and approvals; cumulative staging, exact target diffs, target locks, durable published heads, rollback/recovery and unchanged-source postconditions | Historical in-place records cannot become separate-target approvals; unknown nonempty targets require explicit resolution |
| W02 Faithful Ember behavior | Bounded syntax translation preserves supported defaults, actions, templates and styles; rejects unknown constructs; typed source-grounded initial generation for declared implementation scopes through CLI/MCP | Real route/service/model/integration/business behavior must be generated and accepted through the agent; there is no claim of complete deterministic Ember coverage |
| W03 Foundation readiness | Preset-owned lint/test configuration and shell smoke test; finite matching validation catalogs; current Angular 21 default and explicit Angular 17 compatibility preset | The operator provisions installed toolchains/dependencies; no unapproved installation commands or target patches |
| W04 Architecture precedence | Owner-signed manifest seals source revision/fingerprint, exact draft and ADR bytes; current published foundation is universal for functional tasks; architecture-owned configuration stays in foundation scope | Accepted flags alone convey no authority; replacements retain historical signed ADR bytes |
| W05 Scope fidelity | Exact bundle membership selected before extraction; qualified pod/feature output identities and relative service imports | Unsupported selected bundles fail closed; unrelated unsupported bundles do not contaminate a bounded task |
| W06 Team continuity | Public onboarding API/CLI/GUI, explicit enrollment/status guidance, enrolled reviewer key selection, Mode A for independent reviewer/native operator handoffs, Mode B account containment | Managed host and OS identity model; trusted administration provisions shared state/trust, not copied user anchors or tokens |
| W07 Governance Git integrity | Signed architecture and selected ADR digests join the existing immutable Git publication verifier; onboarding documents Git/agent offboarding separately | Upstream protected branches, required verifier, force-push and bypass permissions must be configured by the repository administrator; no remote deployment or rejected push is claimed |

GUI continuity now uses actual foundation tasks and distinguishes staged, validated
and published readiness. Decision views show source and exact target identity.
Stage actions explain missing dependencies and initial generation proposals. Git
directory fetching has a shared 20-second total deadline and a 25-second client
deadline, with no partial directory accepted. Idle GUI runtimes refresh changed
configuration/architecture; active work is protected. CLI/MCP clients receive
restart guidance for stale snapshots, including generation submissions.

## Architectural and security details

Dependencies still point inward. Framework parsing, rendering, filesystem
fingerprinting, OpenSSH discovery and subprocess execution remain adapters. New
public boundaries use typed models. The generation host supplies untrusted proposals
with current source citations and exact target files; submission never issues
validation evidence or approval. Content, scope, protected paths, budgets,
prerequisites, architecture and destination are checked again before execution.

Target review old bytes are stored with the proposal and included in its digest.
The canonical target identity selects the global apply lock across operational
state roots. Publication compares the full target against validated staging and
advances its managed head in the durable workflow transaction. Recovery classifies
that bound target, never a substituted source tree.

Native dependency preparation retains full byte digests and supervised process
checks. Copying checks consent and leases at bounded checkpoints, then after copy.
Large tree hashing uses four workers with deterministic ordering and unchanged
per-file content and concurrent-change guards. Opened-file identity is checked
before reading, rather than repeatedly resolving every ancestor. Fingerprint
scans retain lease/access/cancellation fences; short heartbeats cannot shorten
longer interactive leases. Native review uses existing `evidence.read` rather
than requiring validation execution permission. No integrity check is removed.

## Verification

Verification is in progress. Final measured outcomes are recorded here after
the full required gates, installed-tool acceptance and GUI verification finish.
Routine logs are under `reports/workflow-completion-*`; these are local evidence,
not shipped customer/application configuration.

Already measured: destination/foundation/generation focused slice passes; GUI
40 tests pass, with lint/format and rebuilt production assets; genuine OpenSSH handoff accepts an enrolled signature
across OS-account contexts while refusing Mode B and wrong-purpose envelopes.
An earlier UI worker-start timeout under concurrent acceptance load was followed
by a successful final run. Native revocation and read-only evidence inspection
regressions pass. Full-suite and installed Angular acceptance results remain pending.

## Owner prerequisites and real-application acceptance

The current [operations guide](../docs/migration-workflow.md) specifies what the
owner prepares and what developers/reviewers receive. Actual owner enrollment,
trusted provisioning, real source-specific generation, browser/business journeys
and remote Git protections remain deployment/application acceptance actions.
No selected Ember source was modified, no target application was hand-edited,
and no human approval was simulated on the supplied application. Disposable test
fixtures use explicit ephemeral test authority/consent; they do not prove that the
real application has completed migration.
