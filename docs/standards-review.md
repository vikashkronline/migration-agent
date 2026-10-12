# G1 technical standards evidence

The platform provides reusable, project-neutral migration tooling. The first
standards slice is G1: versioned rule metadata and an exact-artifact standards
ledger integrated with the existing workflow. Only generic technical concepts
belong in platform profiles; external project identity and business-specific
knowledge are excluded.

## Reused behavior and adaptations

The Angular adapter classifies TypeScript, specs, E2E, HTML, styles and other
files and assigns explicit applicable rule IDs. Registry ingestion accepts
`appliesTo` and `safeAutofix` names and all eight observed enforcement modes.
Duplicate IDs, unknown enforcement/evaluators, invalid profile combinations and
unsupported Angular applicability are rejected.

The platform derives the inventory from the stored ChangeSet and produces one outcome for each
applicable rule by performing a deterministic check or reconciling existing
execution evidence. A reviewed flag or count cannot stand in for a check.
Unsupported checks remain `BLOCKED`; manual obligations remain `PENDING_MANUAL`.
Reports contain candidate-byte hashes and evidence references, not source snippets.

The bundled `ember-angular-baseline` profile contains three adapted rules:

| Rule | Adopted behavior |
| --- | --- |
| `RULE-FORMAT-001` | Scan complete proposed text for CR bytes; require LF. |
| `RULE-QUALITY-001` | Require recorded lint, typecheck, test and build execution for the exact staged artifact. Registry text never becomes a command. |
| `RULE-MIGRATION-CONTRACT-001` | Record pending review of behavioral parity, bindings, generated DTO preservation and affected consumers. |

Rule IDs identify technical obligations within the selected profile. Bundled
`safeAutofix` flags are false. Imported autofix flags are metadata and grant no
authority. The effective registry digest and profile version identify the checks.
Runtime needs no external reference checkout, Node helper, remote fetch or new
Python dependency to load the bundled profile. See the
[architecture review](../plannings/migration-standards-adoption-review.md).

## Use with the existing workflow

Stage the selected plan step through the existing workflow, then run:

```text
agent validation standards step-001 --project-root "<source-repository>" --plan "<plan-id>" --state-dir "<external-state-directory>" --staging-root "<external-staging-root>"
```

Use the same external state and staging roots as stage/validate. The command reads
the current stored staged artifact and emits a typed JSON report on stdout.
It runs no package script, model call, source mutation, repair, approval action or
lifecycle transition. Ordinary platform state initialization may occur when opening
the shared runtime; existing workflow evidence is unchanged.

Optional `--registry "<registry.json>"` selects a bounded strict registry for this
report only. It does not install rules, persist overrides, weaken policy, fetch
references or change the approved plan. Linked/junction, sensitive, binary,
malformed and secret-shaped registry inputs are rejected. External rules
without implemented evaluators cannot become passes. Mixed manual/automated
enforcement remains blocked until its complete semantics are implemented.
Upstream `AST` scope is preserved as a visible obligation on each changed file;
G1 supplies no source AST evidence, so those checks always remain blocked.

The shared ApplyService checks project/plan ownership, source revision and clean
fingerprint, policy digest, candidate digests and exact staged contents. When
validation exists, it loads canonical immutable ValidationExecution evidence,
checks artifact/results/digest binding and invokes the existing backend verifier.
Missing execution becomes a blocked obligation; stale or invalid evidence is
rejected. Source, staging, plan and record bindings are checked again before return.

The JSON binds project/run/plan/step, record version, base revision and working-tree
fingerprint, ChangeSet, policy, staging, validation and effective registry digests.
File/rule ordering is deterministic. Totals are derived from outcome rows. Every
changed path, including deletions, remains visible. Renames, case-colliding paths,
binary/non-UTF-8 or secret-shaped content and candidates over the existing
100-file/32-KiB limits are rejected. A file with no applicable rule blocks
acceptance rather than being counted as reviewed.

| Exit code | Meaning |
| --- | --- |
| `0` | Selected profile checks completed without blocking/error findings. |
| `1` | `FAIL` or `BLOCKED`; failed checks are still visible inside a blocked report. |
| `2` | Invalid, unavailable, unsupported or stale registry/artifact/execution context. |

`BLOCKED` takes precedence when any obligation is incomplete. The default profile
therefore remains blocked after machine gates pass: G1 records semantic obligations
and does not ingest manual attestations. A narrower explicit registry may pass its
own checks. Every report sets `report_only: true`. A report does not satisfy or
replace existing human approval/apply gates, nor become a mandatory new runtime
approval prerequisite.

## Architecture and limits

Domain models own immutable metadata/outcomes. The application reconciles typed
rules, candidate bytes and execution records. Angular applicability and evaluators
live in the adapter behind RuleEvaluatorPort. The existing ApplyService supplies
guarded stored evidence; the CLI selects the registry and formats the result.
There is no second run store, repair budget or learning service.

Offline tests use disposable Git repositories and explicit execution fixtures.
They cover parsing, file hashing, source/plan/artifact/staging drift, partial
validation, pending review, concurrent plan changes, typed CLI output and source/
approval preservation. Packaging checks that the registry ships in the wheel with
source-identical bytes. Windows verification does not establish live Linux acceptance.

G1 does not add comprehensive Ember parsing, computed/mixin/lifecycle translation,
UI widget generation, spec selection, semantic autofix, MR/GUI remark resolution,
manual attestation ingestion or learning-driven rule promotion. Later slices remain
separate implementation scope.
