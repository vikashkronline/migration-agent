# penalite-frontend — initial manual GUI acceptance review

Date: 2026-10-07

Scope: supplied desktop/mobile screenshots, read-only inspection of the selected
source and external SQLite store, and comparison with the implemented GUI. No
source, workflow state, staging or GUI code was changed for this review.

## Outcome

The GUI is successfully running as a fresh, authenticated inspection session for
the intended Ember repository. The displayed absence of progress is truthful.
Launching the GUI initialized external operational storage and bound an existing
source directory; it did not adopt/scaffold an application or create a migration
plan. The user journey currently stops at an insufficiently guided empty state.
The real application's migration has separate, confirmed implementation blockers.

## Current-state verification

| Check | Observed result | Assessment |
|---|---|---|
| Selected source | `C:\Projects\ISOCEL\Alice\Ember\penalite-frontend` | Matches launcher output and screenshots |
| Bound project ID | `penalite-frontend-10dda7cebadf2d5245b8ca7c` | Matches screenshot URL and current binding calculation |
| Server | Screenshot reports loopback `127.0.0.1:8081`, status running | Port workaround succeeded; no public bind shown |
| Actor/assurance | Screenshot shows `vkumar / MODE_B` | Expected trusted local inspection identity; not evidence of source approval |
| Source/state/staging | Distinct roots; state under `C:\AgentMigration\penalite-frontend\state`, staging sibling | Safe separation is correct |
| SQLite | `checkpoints.db`; read-only `PRAGMA quick_check` returned `ok` | No corruption found |
| Plans / workflows / ChangeSets / operations / journal | All five tables contain zero rows | There is no saved migration task, execution, artifact or completed work |
| Staging | Directory absent | Expected before first staging; no failed staging implied |
| Governance | No `.agent/manifest.json`, `.agent/policy.json` or `.agent/project-work.json` | Initial read-only GUI may operate without them; adoption/hierarchy definition has not occurred |
| Knowledge | No eligible source governance/architecture reference directories found | Empty knowledge is expected; generic reader does not import every source README/report |
| Source Git | Clean during verification | No migration changes were made |
| Existing assessment | Local inventory report exists in the agent workspace | Its 2,268 eligible files are not automatically imported as workflow completion |
| Source framework | Ember source 3.8.1 / CLI 3.8.3; no root `angular.json` | Existing application remains Ember; Angular target foundation is unestablished |

The green **Current snapshot** badge concerns the freshness of the GUI's state
read. It does not mean the source is migration-ready, healthy, validated or complete.

## GUI findings

| Priority | Finding | Suggested correction |
|---|---|---|
| P1 | Empty overview gives no actionable next step | Explain “Project opened; no migration plan saved,” show discovery/analysis/planning sequence, and provide an authorized action or exact CLI/host handoff |
| P1 | Repository-specific blockers are absent | Surface recorded assessment and capability coverage, including unsupported pod layout and missing target setup; distinguish planning availability from staging eligibility |
| P2 | Project name appears twice in breadcrumb | The shell renders a project link and then the breadcrumb's project node; render it once |
| P2 | Workflow sections appear for every node | Project overview should emphasize overview/readiness/knowledge and next steps; expose Steps/Checks/Artifacts/Decision in relevant task contexts, or explain unavailable sections |
| P2 | Root overview lacks foundation/work/knowledge dashboard cards | Those headers are root siblings (`parent_id=None`), while Summary renders only direct children of the selected node; provide explicit root-group cards or reconcile ownership projection |
| P2 | Repeated “unknown” badges give little explanation | Keep truthful backend status, but describe the cause per context: no definition, no plan, not assessed, or no evidence; show the required next action |
| P2 | Existing inventory is disconnected from the GUI | Add a typed, source-bound assessment/evidence projection or import/reference flow; do not turn discovered code into fabricated work completion |
| P3 | Dense mobile header and duplicate Ask affordances | Tune priority/spacing and contextual shortcuts during manual acceptance; current captured content is readable |

Confirmed locations: `ui/control-center/src/app/workbench/shell/project-shell.html`
(breadcrumb), `workbench/item/item-page.ts` (unconditional section list),
`workbench/item/summary/summary-page.html` (empty state/direct-child cards), and
`src/migration_agent/adapters/workbench.py` (root projection/record-only scope).

The screenshots demonstrate persistent desktop navigation, full-width mobile
content when navigation is closed, and a drawer with background dimming and close
control. They do not establish focus containment/return, Escape/backdrop behavior,
keyboard operation, zoom/reflow or screen-reader acceptance. Those need interaction
checks. The real empty-project onboarding has not been fully satisfied merely
because the automated baseline/build tests passed.

## Migration readiness blockers

1. There are 13 feature/pod `component.js` files under `app/features`; the current
   Ember extractor scans `app/components/*.js` and discovers zero supported bundles
   for this source. It needs an explicitly authorized, tested extension.
2. The 34 Ember service JavaScript files are not covered by the currently provided
   AngularJS service extractor. Pilot dependencies also need explicit support for
   the required routes/controllers, mixins, helpers and application-specific add-ons.
3. A runnable Angular target foundation and its relationship to this Ember repository
   are undecided/unimplemented. Creating Angular component files alone cannot replace
   package/build/routing/dependency configuration or establish business parity.
4. The source `build` script runs `ember deploy production`, and `archive` publishes.
   Define target-only validation instead of running release/deployment scripts.
5. The last supplied doctor output showed restricted execution, no configured native
   toolchain/dependencies and no model configuration. Current launcher configuration
   is not proven by the overview screenshot. Provisioning, execution consent, browser
   review coverage and exact source approval still need to be established for a pilot.

These are migration implementation/configuration needs, not evidence of a corrupt
GUI project or a source migration that already started and failed. No failed run
or apply attempt exists in the inspected store.

## Recommended next user sequence

1. Keep the GUI available for inspection and use a second normal-user PowerShell
   terminal with the same source, state and staging paths.
2. Review the already generated inventory and choose one small business feature for
   the pilot. Record expected behavior, API contracts, dependencies and acceptance
   criteria. Optionally declare project work in Git with planned/unverified status.
3. Choose the Angular target layout and an approved reasoning route (IDE/MCP or
   configured standalone provider). Create/review a grounded plan in the same store;
   a saved plan should make workflow entries visible, but does not prove stageability.
4. Resolve the confirmed discovery/transformation and target-foundation gaps before
   attempting automatic conversion of this application's feature code. This is the
   current implementation stop point, rather than repeatedly invoking `migrate`.
5. Provision validation tools/dependencies and browser coverage for the pilot. Then
   stage, inspect the exact diff, personally authorize execution, validate/review,
   personally approve the exact artifact and apply through the guarded runtime.
6. Review/commit the result and create a fresh plan for the next base. Do not present
   fake checks, declarations or an empty run store as verified migration progress.

The [project-specific guide](../docs/penalite-frontend-migration-start.md) contains
the current commands and conditional later execution sequence. Developer comments
and **Request changes** remain deferred per the user's later-stage decision.
