# Governed migration workflow

This guide describes the local, managed-workstation workflow. The Ember source is
read-only throughout. An isolated staging workspace supplies validation evidence;
approved files are published into a separate cumulative target. Governance and
operational state are distinct from both application repositories.

## Owner preparation

1. Provision a clean, committed source checkout, an external governance Git
   repository, and distinct state, staging, target and external trust directories.
   Linked roots and overlapping paths are rejected. Use a new state directory for
   an independent migration; do not reuse another project's initialization.
2. Run `agent init --help` and initialize with the explicit source, staging and
   state paths. Run `agent access bootstrap --help` to enroll the owner in the
   external governance project. Bootstrap and key enrollment are trusted-terminal
   operations. Private keys stay outside the project.
3. Configure the separate target in Control Center Settings or the configuration
   CLI. Shared restrictions require an exact signed proposal; local paths are
   workstation configuration constrained by those restrictions. Check the
   effective values and their provenance before starting execution.
4. Run `agent doctor`. Choose restricted inspection, an approved container image,
   or a verified native toolchain and dependency tree. The owner/administrator
   installs trusted tools and prepares dependencies outside source and staging.
   Selecting native mode does not authorize process execution; exact human consent
   is still required. The agent never runs model-generated install commands.
5. Protect the governance remote's branches and required checks using the Git
   provider. The agent verifies signed governance activation and publication; it
   cannot prevent someone with upstream write permission from pushing a branch.
   Configure provider permissions and required governance verification independently.

See [configuration](project-configuration.md), [access management](rbac-and-users.md)
and [native validation](native-validation.md) for the full command options.

## Architecture and foundation

In the Foundation wizard, inspect the source, select a registered preset, resolve
or explicitly defer unmapped packages, and review the resulting ADRs. Prepare the
architecture approval. The GUI returns exact terminal arguments for the owner;
it does not sign them. Confirm the concrete proposal using `agent access approve`
and refresh status. The active signed manifest binds the draft, source revision,
source fingerprint and selected ADR bytes. Editing an accepted flag in Git cannot
authorize a different foundation. A replacement decision records supersession
without rewriting historical signed ADR bytes.

The current default preset is Angular 21 with Angular CLI Vitest. The explicit
Angular 17 compatibility preset retains its own commands and integration; its
historic identifier does not indicate current support. Preset-owned package
coordinates take precedence over legacy package mappings. See the primary
[Angular release schedule](https://angular.dev/reference/releases) and
[testing documentation](https://angular.dev/guide/testing).

A grounded recorded plan must contain a foundation step. The wizard lists actual
eligible plan/step records. Stage that step, inspect its exact files and target
base, authorize the selected execution backend, and run validation. The generated
base includes lint configuration, test configuration and a shell smoke test.
Restricted inspection cannot produce executable validation evidence.

Review the exact validated artifact in the Decision view. A human signs through
the CLI, then an operator applies through GUI/CLI/MCP. Publication updates the
managed target head. Functional tasks require a published foundation for the same
target, active architecture and policy, and published declared prerequisites.
Staged or merely present files do not satisfy that gate.

## Developer, reviewer and operator handoffs

Git membership is a directory source, not agent authentication. The owner imports
or adds a principal, reviews its role grants, verifies OS identity and public-key
possession, and activates membership through the signed access workflow. Pending,
expired or suspended members cannot execute their declared grants.

Users & Access provides an **Onboarding information** view; the CLI equivalent is
`agent access onboarding SOURCE --principal PRINCIPAL`. Share this public packet
with the approved repository URLs/version, current source revision, agreed roots,
task IDs, accepted decisions and business acceptance criteria. Provision shared
operational state and trust through the trusted administrator on the managed host.
Do not distribute private keys, another user's local anchors or browser tokens.
Each person launches their own local session as their enrolled OS identity.
The packet's `project_id` names the governance access binding. Obtain the workflow
project ID from the connected host's inventory before making scoped MCP calls;
do not substitute the governance ID or guess task identifiers.

| Work | GUI | CLI/core or connected host | Owner/manual responsibility |
| --- | --- | --- | --- |
| Configuration | Effective values, checks, local edits, signed shared proposals | Typed resolution, validation and activation | Trusted tool/dependency provisioning |
| Membership | Directory import, roles, proposals, onboarding | Enrollment proof and owner signature | Upstream Git permissions and OS/state administration |
| Architecture | Draft, ADR review, proposal and readiness | Exact owner signature and verified contract | Resolve architecture and package questions |
| Planning/generation | Browse tasks, dependencies and evidence | Grounded host/CLI/MCP proposals; deterministic adapters | Define business acceptance and supported scope |
| Staging/validation | Stage, run checks, inspect logs/results | Fenced commands and persisted evidence | Native consent or approved container readiness |
| Review/publication | Diff, checks, human handoff, apply | Exact CLI signature; guarded cumulative target publication | Reviewer judgement and final business acceptance |
| Recovery | Durable operation/status diagnostics | Reconciliation and explicit CLI recovery | Resolve ambiguous drift using reviewed evidence |

Mode B deliberately stays within one OS account. When a reviewer cannot apply,
the review challenge requires Mode A with their enrolled key. When another active
principal can validate, native execution consent requires the operator's Mode A
signature so an independent developer can consume it. Owners with the full local
workflow retain the eligible local confirmation path. Remote identity login,
cross-machine trust enrollment and distributed state synchronization are not part
of this local architecture.

Native evidence inspection uses the existing `evidence.read` capability and never
runs application code. Consent and input freshness are still checked. Long input
fingerprints retain lease/access/cancellation fences, and heartbeat renewal extends
the existing lease rather than shortening an interactive review window. Shared
operational state remains a trusted administrative boundary; local RBAC does not
protect it from arbitrary OS processes with direct write access.

## Functional migration

Execute the plan in topological order. Bounded deterministic Ember transformations
preserve supported state defaults, action bodies, templates and component styles;
they reject unknown semantics. Classic and pod components use qualified source
identities and distinct output namespaces. A rejection is an actionable boundary,
not permission to substitute a generic layout or an empty method.

For complex source behavior, declare `scope: implementation`, exact `target_files`
and acceptance criteria in a grounded plan. The connected generation host reads
`migration_implementation_context`, creates a source-grounded typed proposal, and
calls `migration_submit_implementation`. CLI equivalents are
`implementation-context` and `submit-implementation`; proposals belong in external
state/artifact directories. The core verifies source citations, current target
base, architecture, scope, budget and prerequisites. This initial-generation path
does not mint validation or approval. Architecture-owned configuration changes
must use a foundation step. Normal stage, validate, review and apply follow.

If validation fails, inspect the recorded checks and bounded diagnostics, submit a
grounded repair within the allowed scope/budget, and validate the new artifact.
Earlier approval becomes stale. Configuration or architecture changes require a
fresh runtime; the GUI refreshes idle runtimes and refuses changes while work is
active. Long-lived CLI/MCP clients receive restart guidance.

## Publication, drift and completion

Reviews bind the source, destination root and destination fingerprint, architecture,
policy, plan and exact bytes. Publication uses a lock shared by the canonical target
identity, even across state roots. It backs up affected target files, applies the
approved changes and compares the complete target against validated staging while
checking the source stayed unchanged. Subsequent tasks stage from that cumulative
target. Unknown nonempty targets, target switches and unreviewed drift fail closed.

Recovery inspects the bound destination and source. Historical in-place checkpoints
cannot be reused as separate-target approvals. Ambiguous partial writes require
operator resolution; a retry does not silently adopt them as a new baseline.

Workflow completion requires every required step to be applied with current checks,
plus the project's actual route/service/integration and business acceptance tests.
A passing fixture or an empty shell is not proof that a real application migration
is complete. Unsupported behavior is handled through grounded generation or an
explicit adapter extension, always through the agent's normal gates.
