# Migration standards adoption plan

Date: 2026-10-08  
Status: G1 technical standards reporting implemented; later slices proposed  
Authority: [Platform master plan](final/agent-platform-master-plan.md) and
[phase status](../docs/phase-status.md)

## Intent and knowledge boundary

Reuse suitable technical implementations and adapt them to this migration agent's
existing workflow. Reference materials inform engineering choices; they are not
runtime dependencies or authority over project policy. Shared agent knowledge,
profiles, prompts and shipped assets exclude reference-project identity, business
details, checkout paths and project-specific conventions.

Keep the neutral core, framework adapters, selected target profiles and actual
target-project configuration distinct. Only configuration explicitly belonging to
the selected migration target can introduce its own conventions. Importing a
reference implementation never activates its business rules.

## Reusable technical concepts

| Concept | Integration |
| --- | --- |
| Versioned rule metadata | Strict typed registry; explicit applicability and evaluator support |
| Exact file/rule coverage | Derive inventory from stored ChangeSet; require evidenced outcomes |
| Deterministic specification selection | Source-backed signals, selected spec hashes and explicit conflicts |
| Bounded context compilation | Relevant dependency context, input hashes and reserved output budget |
| Migration contract reconciliation | Source/target inputs, outputs, actions and affected consumers |
| Semantic migration analysis | Adapter-owned source representation and verified neutral lowering |
| Curated learning | Existing evidence-backed, human-approved project knowledge lifecycle |

## Architecture and safety

- Dependencies point inward. Framework-specific behavior stays in adapters.
- Typed models cross every public boundary. Model output remains untrusted.
- Source repositories remain read-only during analysis/proposal generation.
- Source, state/artifacts and staging roots remain distinct and guarded.
- Existing ChangeSet, validation, policy, human approval and controlled apply
  contracts own authority; imported rule prose is never executable.
- Reuse existing repair budgets, checkpoints and learning services.
- Unsupported syntax, uncertain semantics and missing evidence fail closed.
- Persist repository-relative paths in POSIX form and sort machine artifacts.
- Tests remain offline and require no live provider credentials.

## Implementation sequence

1. **G1 — Rule registry and standards evidence (complete).** Strict registry
   ingestion; deterministic line-ending checks; reconciliation of recorded
   validation profiles; explicit pending manual obligations; report-only CLI
   integration with the existing guarded staging service. See the
   [implementation report](standards-g1-implementation-report.md).
2. **G2 — Specification selection and context binding (proposed).** Stable
   source signals, rule/spec reference validation, hash binding, conflict handling
   and bounded dependency context. No model-generated selection authority.
3. **E1/E2 — Narrow source analysis and neutral lowering (proposed).** Verify
   parser fidelity and portable packaging against fixtures. Keep Ember-specific
   analysis within the adapter. Implement one supported semantic construct at a time.
4. **E3/E4 — Verified Angular generation (proposed).** Resolve target versions
   and APIs from target evidence. Add computed/form/action/mixin/lifecycle support
   through separately accepted fixtures. Never bundle another project's widgets,
   business mappings, names or styling.
5. **Later review integrations (proposed).** Evidence-backed test generation,
   advisory quality metrics and authorized artifact-bound feedback. Extend the
   shared workflow rather than creating a second orchestration or learning system.

No proposed slice is implementation permission. Each requested slice needs focused
tests, all six repository quality gates and accurate documentation updates before
completion. Stop at the authorized phase boundary.

## Current limits

G1 reports technical standards over exact staged artifacts. Its default profile
records semantic review as pending and does not authorize apply. It adds no
comprehensive Ember parser, project-specific UI mapping, semantic repair or manual
attestation acceptance. See [operations](../docs/standards-review.md) and the
[architecture review](migration-standards-adoption-review.md).
