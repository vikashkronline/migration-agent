# Control Center — Common GUI implementation report

Date: 2026-10-07

Status: Authorized common GUI completed, including modular Angular 21 features, optional typed project-work definitions and recorded-context Ask. Required gates passed. Remaining product boundaries are explicit below.

The subsequently selected embedded read-only diff viewer is tracked in its
[implementation report](control-center-read-only-diff-implementation-report.md).
It adds base/proposal comparison to Artifacts without a full review-write workspace;
its final regression evidence supersedes the earlier preview-only review boundary.

## Completion amendment — modular Angular and generic project work

This amendment supersedes the earlier baseline's missing project metadata and
unavailable GUI Q&A. The historical baseline evidence is retained below.

- Standalone, OnPush, zoneless Angular features replace the monolithic component.
  `core`, `shared` and `workbench` separate infrastructure, reusable presentation
  and lazy routed features. Strict TypeScript/templates, typed HTTP errors, global
  errors, route guards and a route-scoped signal store enforce those boundaries.
- URLs own project/item/section and run/artifact pins, including legacy-link
  redirects. Reads cancel on selection changes; search is debounced, polling is
  cleaned up on destruction, and branch loading uses explicit bounded pages.
  Lost command delivery retains the original request identity for receipt recovery.
- The user-selected optional `.agent/project-work.json` defines generic objectives,
  foundation/module/knowledge groups, ownership, criteria and planning dependencies.
  Linked records appear once with stable identity and their actual workflow state.
  Invalid declarations warn without hiding canonical records; missing evidence
  stays inspectable and nonexecutable. Declared completion cannot inflate verified
  rollups or replace runtime dependencies, policy or approval.
- Ask returns scoped, revision-bound recorded facts with citations, explicitly
  reports missing evidence and provides the existing provider-assisted CLI handoff.
  It does not invoke providers or implicitly export source. Questions and definitions
  pass the existing secret-screening boundary.
- Reusable native modal, feedback and status components cover the responsive drawer
  and workflow confirmations. Actual browser captures were inspected. Plain CSS,
  Bootstrap utilities and persisted light/dark preferences meet current styling needs;
  SCSS adds no useful abstraction here. Script CSP remains intact.

| Final completion gate | Result |
|---|---|
| `uv sync --all-groups` | 69 packages resolved, 68 checked |
| `uv run pytest` | **582 passed, 3 skipped in 4526.48 seconds**; includes actual loopback/Chromium journey and recorded-context Ask |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | 253 files already formatted |
| `uv run mypy src` | 119 source files passed |
| `uv run migration-agent doctor` | Exit 0, schema version 1, status `ok` |
| Angular lint / formatting | `npm run lint` and `npm run format:check` passed |
| Angular unit tests | **12 passed in 6 files**, Angular TestBed/HTTP/routing/state with Vitest 4.1.11 |
| Angular production build | Passed; initial **531.03 kB raw / 107.78 kB estimated transfer**, features and Mermaid loaded lazily |
| Production browser journey | Passed: scoped Ask, history/pins, cancelled stale reads, inert artifacts, strict diagrams, recovery, mobile focus/backdrop/Escape/resize, reflow/theme and bounded paging |
| Wheel / whitespace | Wheel built; all **62 production assets** byte-for-byte equal to source build; `git diff --check` passed |

The final browser fixture loaded all 1,000 tasks through explicit page requests in
**5727 ms** while other quality gates were active. This includes user-simulated
page clicks and differs from the earlier automatic branch expansion measurement;
the two are not comparable benchmarks. The initial page stays bounded to 100.
Backend additions cover invalid graphs, duplicate ownership, missing evidence,
stable identity, declared versus actual completion, stale/cross-project answers,
extra authority fields and credential-shaped input. The existing real guarded
apply regression now also verifies nested generic group completion rollups.

Remaining boundaries are intentional: human approval/signing and execution/provider
disclosure consent retain trusted CLI/host channels; full detailed review stays in
the IDE/CLI; provider reasoning uses its existing handoff. Knowledge preview remains
bounded, superseded artifact links report invalidation rather than complete archival
retrieval, and this Windows Chromium evidence does not claim all-browser,
screen-reader/WCAG, live Linux or binary-sidecar acceptance. No user-selected target
source was migrated or external site published by this implementation.

See [operations](../docs/control-center.md),
[project-work schema and semantics](../docs/project-work.md),
[Angular development](../ui/control-center/README.md) and
[phase status](../docs/phase-status.md).

## Earlier common baseline checkpoint (historical)

The following verification predates the completion amendment above. Its metadata
and Q&A limitations are superseded by that amendment.

## Authorized outcome

The hierarchical UX review now has an implemented common shell and typed
application boundary over existing canonical migration workflows. It replaces
the handwritten static GUI and corrects legacy GUI state/approval/apply wiring.
The independent review and design wireframe remain historical artifacts.

| Concern | Implementation |
|---|---|
| Common boundary | `application/workbench.py`: typed project/group/task/reference views and `WorkSourcePort`; no frontend, migration, filesystem or persistence imports |
| Canonical adapter | `adapters/workbench.py`: bound plans, actual tasks, lifecycle/dependencies, exact artifact/check evidence and truthful unloaded totals |
| Queries | Versioned `/api/v1/workbench` metadata/tree/detail/events/image routes; scoped, revision-bound detail and 100-item pages |
| Actions | Typed command with current revision and request identity; shared guarded stage/validate/apply; durable retry receipts |
| Invalidation | Transactional SQLite journal observes CLI/MCP writes across processes/restarts; scoped cursor plus snapshot reconciliation and reference-content revisions |
| Evidence | Bounded redacted proposed contents/operation tails; lazy scoped/hash-verified PNG; strict noninteractive Mermaid displayed as an image |
| Explorer | Selectable groups/tasks/references, separate expansion, ancestors, project search/attention and paged run/task context |
| Exact navigation | Stable direct load/history; run/artifact pins, explicit invalidation and ignored superseded responses |
| Responsive layout | Persistent desktop sidebar; closed mobile overlay drawer, native focus containment/inert background, scroll lock, selection/Escape/close/backdrop/resize handling |
| Review | Checks/artifacts/activity/decision views, recorded milestones, unavailable-action reasons, external IDE and human-terminal approval handoff |
| Trust | Launcher-resolved actor/grants, bound project, loopback host/origin validation, independent CSRF, cookie reload and strict script CSP |
| Build | Real Angular AOT workspace, Signals/OnPush, local Bootstrap, reproducible npm lock and hashed offline assets |

The legacy actor/plan-derived approval hash and notification-only apply are
disabled. Bound GUI sessions cannot use their old endpoints or process-local
event transport. Six unused legacy frontend components/services were removed,
including obsolete approval and full-review wiring. Approval remains the existing
human-only CLI path, with policy-required signing and shared guarded apply.

### Earlier baseline verification

| Final gate | Result |
|---|---|
| `uv sync --all-groups` | 69 packages resolved, 68 checked |
| `uv run pytest` | **572 passed, 3 skipped in 640.78 seconds**; includes real loopback/Chromium integration |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | 248 files formatted |
| `uv run mypy src` | 117 source files passed |
| `uv run migration-agent doctor` | Exit 0, schema version 1, status `ok` |
| Angular production build | Passed with Node 20.19.2, compatible TypeScript 5.9 and offline bundled assets |
| `npm test` | Production Chromium interaction/layout checks passed; 1,000-task expansion measured **747 ms** in the final run |
| Final real-server browser rerun | Passed after the stylesheet/CSP correction |
| Whitespace check | `git diff --check` passed |

Backend regressions cover foreign scope, forged actor/approval, missing grants,
overlapping roots, stale revisions, durable cross-process updates, cookie reload,
malformed origins, independent CSRF, traversal, shared guarded apply, durable
retry, capture-scope mismatch and tampered PNG. The 1,000-task canonical fixture
checks truthful unloaded totals and nonoverlapping pages. Snapshot plus initial
search measured approximately **0.17 seconds** locally.

Offline Chromium exercises the production bundle with generic documentation and
migration fixtures: direct load/history, artifact invalidation during confirmation,
exact command payload, delayed selection race, recovery restrictions, mobile
focus/backdrop/Escape/resize, 320/375-width reflow, theme, diagnostics/run context,
Mermaid and 1,000-task paging. Final layout measurement is recorded below.

A separate Python integration test starts the actual loopback server/canonical
external store, renders the real bundle, inspects checks/decision, reloads its
cookie-authenticated link and verifies unknown foundation. Source files remain
unchanged. No remote network or provider credential is required.

Visual inspection found two issues beyond JavaScript behavior: Angular's HTML
sanitizer removed SVG, and critical-CSS optimization generated an inline `onload`
blocked by CSP. Strict Mermaid now renders as an image without bypassing document
HTML sanitization. Critical-CSS inlining is disabled; browser assertions check
actual responsive visibility, absence of stylesheet handlers and rendered dark
background. CSP was not weakened.

The final initial bundle is approximately **417 kB raw / 76 kB estimated transfer**.
Mermaid loads on demand; its existing CommonJS optimization warnings remain
visible and do not prevent compilation.

### Earlier baseline product boundaries

- Canonical production records currently describe migration plans/tasks. Arbitrary
  module, acceptance, ownership and technical-readiness entities do not yet exist;
  the common port is their future integration seam. Unknown scope is not fabricated.
- Execution/disclosure consent, browser review/repair and source approval keep
  existing CLI/host entry points. This slice adds inspection and guarded requests,
  not new consent channels, source approval tools or autonomous recovery.
- Proposed contents are a bounded review aid; exact detailed diff review stays
  with CLI/IDE. No full embedded review environment was introduced.
- Contextual Q&A is explicitly unavailable in this integration. Knowledge preview
  covers up to 100 eligible Markdown/Mermaid references. Old artifact links expose
  invalidation rather than claiming complete archival retrieval.
- Polling uses durable invalidation/refetch rather than WebSocket patches. The
  adapter computes a compact complete projection before paging; measurements
  establish this fixture's behavior, not unlimited scale or mandatory virtualization.
- Windows Chromium verification is not screen-reader/WCAG certification, all-browser
  or live Linux acceptance. The wheel packages GUI assets; this amendment does not
  claim a verified PyInstaller binary release.

See [operations](../docs/control-center.md), [architecture](../docs/architecture.md),
[phase status](../docs/phase-status.md) and the
[UX specification](control-center-tree-ux-wireframe-plan.md). Only disposable test
repositories were modified by apply regressions; no user-selected target-source
migration or external publication was performed.
