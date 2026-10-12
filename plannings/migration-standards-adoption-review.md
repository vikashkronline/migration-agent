# Migration standards architecture review

Date: 2026-10-08  
Status: Technical review; G1 implemented under separate user authorization

This review retains reusable engineering decisions and excludes reference-project
identity and business context. The [platform master plan](final/agent-platform-master-plan.md)
governs architecture. [Phase status](../docs/phase-status.md) owns implementation
and measured acceptance. See the [adoption plan](migration-standards-adoption-master-plan.md)
and [G1 implementation report](standards-g1-implementation-report.md).

## Required alignment

### Keep mechanisms separate from project conventions

Rule/evidence machinery belongs to the neutral platform. Ember semantics belong
to the migration adapter. Angular conventions belong to a target-version profile.
Business-specific behavior belongs exclusively to the selected target's explicit
configuration and evidence. Shared knowledge must not contain another project's
identity, business mappings, widgets, colors, names or directory requirements.

### Distinguish rule metadata from implemented checks

Strict ingestion must cover known field aliases and enforcement modes without
coercing unknown values. A rule written in prose is not automatically a machine
check. Mixed manual/automated checks need evidence for both parts. Missing evaluator
support remains blocked; importing a registry confers no execution authority.

Likewise, validating an `ast-map.json` artifact is not proof of a complete compiler
parser. Regex selectors and bounded expression scanners require explicit support
limits. Parser choice needs fixture fidelity, source spans, syntax rejection and
Windows/Linux packaging evidence.

### Require actual per-rule coverage evidence

A reviewed flag, applicable count or populated rule-ID list cannot prove that
checks ran. Derive inventory from the authoritative ChangeSet and record each
applicable rule's outcome, evaluator version and evidence. Missing/manual evidence
blocks acceptance. Handle deletions, renames and unchanged consumers explicitly.
Inventory completeness does not establish semantic correctness.

Bind results to candidate bytes, source/base fingerprint, effective profile,
rule/spec digests and immutable execution evidence. Recompute totals from actual
rows, and reject stale or mismatched contexts.

### Reuse existing authority and knowledge services

Safe-autofix metadata cannot grant mutation authority. Repairs use existing budgets,
policy evaluation, fresh ChangeSet digests, validation and renewed approval where
required. Curated learning already has a project-owned, evidence-backed, human
approval lifecycle; an observed override starts a candidate rather than promoting
durable knowledge automatically. Protected policy and shipped rules cannot update
themselves.

### Preserve framework-neutral contracts

Keep Ember computeds, actions, observers, lifecycle and mixin analysis in adapter-owned
models. Lower supported behavior into typed neutral structures only when needed.
Preserve both existing migration-pair contracts. Unresolved types and behavior must
remain explicit rather than producing guessed code.

Parsing establishes syntax, not behavioral equivalence. Computed setters, collection
dependencies, mixin precedence, service lifetime and cleanup need verified decisions
or blockers. Parent/child and callable-action contracts need source-backed evidence.

### Resolve Angular behavior from target evidence

Prefer modern reactive patterns where compatible, but do not confuse style choices
with API prohibitions. Explicit standalone metadata and decorator inputs remain
valid APIs. Forms need appropriate update notifications; a blanket change-detection
strategy switch does not establish correctness. Align initial and emitted form
values, disabled-control behavior, validation/status changes and teardown.

Keep useful `unknown` narrowing and `never` exhaustiveness checks. Avoid unsafe
untyped output. Verify collection identity, imports, events, cancellation and error
states rather than deriving business intent from labels or inventing target APIs.
See [Angular inputs](https://angular.dev/guide/components/inputs),
[zoneless forms](https://angular.dev/guide/zoneless) and
[TypeScript narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html).

### Measure tests and quality signals

Generated specs do not prove measured coverage or behavior. Use target-provisioned
tools and approved staging commands. Prioritize behavior, error, teardown and
reactivity fixtures. Volume/heuristic scores require calibration before gating.
Feedback needs pending and blocked states, exact artifact anchors and existing
revision/approval contracts; external messages require explicit authorization.

## Disposition

G1 implements the minimum technical registry/evidence slice and report-only guarded
integration. Semantic parsing, specification selection, transformation expansion
and feedback/learning promotion remain separately requested work. Reference-project
provenance and business context are excluded from the shipped agent profile and
its shared instructions.
