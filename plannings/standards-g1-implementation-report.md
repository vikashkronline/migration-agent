# Technical standards G1 implementation report

Date: 2026-10-08  
Scope: First bounded adoption slice authorized by the user's instruction to pick
and adapt reusable technical implementations to the migration-agent workflow.

## Delivered scope

The implementation provides registry/applicability/coverage behavior in an optional
standards report over the existing stored staged artifact.
Strict typed ingestion supports the upstream field aliases and enforcement modes.
The bundled profile adapts LF formatting and recorded command quality checks,
and records source-to-target contract review as a pending obligation. Unsupported
automated checks remain blocked. File/rule inventories and summaries derive from
actual outcome records.

The shared ApplyService supplies existing base, plan, policy, ChangeSet, staging
and immutable execution verification. Command evidence is checked through the
existing backend. Reports perform no execution, approval or source mutation and
do not change the run lifecycle. Source-specific applicability/evaluators remain
in the Angular adapter. No parallel governance, learning or repair system was added.

New command: `agent validation standards STEP --project-root ROOT --plan PLAN`.
Existing external state/staging overrides remain available. Optional `--registry`
selects a report profile without installing or activating project policy.
See [operations and explicit limits](../docs/standards-review.md).

## Technical scope and isolation

- File typing, applicability and exact inventory reconciliation produce actual
  evidenced outcomes; reviewed/evaluated flags alone are insufficient.
- Strict registry field aliases and enforcement metadata support external JSON,
  while the bundled technical profile has its own version and effective digest.
- Source/target contract reconciliation is a pending manual obligation until
  deterministic semantic verification is implemented.

Only reusable technical concepts are embedded. External reference project names,
checkout locations, business conventions and source-project provenance are excluded
from runtime profiles and shared agent documentation. No external business mappings,
custom widgets, naming conventions or styling specifications are bundled.
See the [architectural review](migration-standards-adoption-review.md).

## Verification

All six required gates passed on Windows/Python 3.12.14:

| Gate | Result |
| --- | --- |
| `uv sync --all-groups` | 69 packages resolved; 68 checked |
| `uv run pytest` | **636 passed, 3 skipped in 597.14s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 273 files |
| `uv run mypy src` | Passed; 124 source files |
| `uv run migration-agent doctor` | Exit 0; status `ok`, schema version 1 |

The full offline suite includes 35 new focused cases. These cover malformed and
unsupported registries, omitted outcomes/evidence, actual LF failures, absent/
partial/failed command evidence, source/plan/artifact/staging drift, concurrent
plan edits, typed CLI output and preservation of approval/source state.

The inspected external registry loads with all 51 rules and eight enforcement
modes. Source AST obligations remain explicitly blocked. An offline wheel build
succeeded; all seven adopted code/profile entries match final source bytes.
Documentation links and whitespace checks pass. This completes the bounded G1
reporting slice; no later adoption phase is included.

No claim is made for later G2–G6/E1–E5 capabilities, manual-attestation acceptance,
mandatory apply enforcement, live Linux execution or target semantic equivalence.

## Neutral-knowledge amendment (2026-10-08)

The user required reference-project identity and business details to stay outside
the agent. The bundled profile is now `1.0.1` with no reference provenance; external
registries default to the neutral identifier `external-registry`. Technical docs
and plans have neutral names and content. Original reference documents are preserved
outside the workspace. AGENTS.md carries the isolation rule for subsequent work.

The focused suite passed **36 tests in 35.57s**. Dependency sync, Ruff, formatting,
strict mypy and doctor passed; the offline wheel was rebuilt and its sanitized code/
profile bytes verified. Agent-facing adoption material passes identity/business
selector scans and link checks. The full suite table above records the preceding
G1 implementation; this naming/provenance amendment used focused regressions.
