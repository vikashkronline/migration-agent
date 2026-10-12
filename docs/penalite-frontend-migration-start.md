# Starting the penalite-frontend migration

Source: `C:\Projects\ISOCEL\Alice\Ember\penalite-frontend`

Assessment date: 2026-10-07. This guide starts discovery/planning and GUI inspection.
The current automatic transformer does not yet support this application's component
layout, so the execution section is conditional on resolving the gaps below.
No migration, provider call, package installation or source modification was
performed while preparing this guide.

## What was verified

- The repository was clean before and after read-only inspection.
- `ember-source` is 3.8.1 and `ember-cli` is 3.8.3.
- Deterministic inventory identified `ember-classic` and 2,268 eligible files.
- There are 13 `component.js` files under `app/features` and 34 JavaScript files
  under `app/services`. The current Ember component extractor found **zero**
  supported standard-layout bundles: it scans `app/components/*.js`, with templates
  under `app/templates/components`. The service extractor currently provided is
  for AngularJS; Ember service conversion must not be assumed supported.
- The Ember `build` script runs `ember deploy production`; `archive` also publishes.
  They are deployment/release commands, not a safe target validation setup.
- No `.agent/manifest.json` exists in the source. Governance defaults permit initial
  read-only inventory and GUI inspection without adopting the repository.

The generated inventory is in the agent workspace at
`reports/manual-start/penalite-frontend/inventory/inventory.json` and `inventory.md`.
These files are reports, not migration plans or successful validation evidence.

## 1. Open a persistent PowerShell terminal

Open Windows Terminal / PowerShell as your normal user. Run the executable with
arguments inside that terminal. Double-clicking the console launcher can open a
temporary window that closes when the command exits; it does not start the GUI.
Native validation rejects elevated execution.

Keep the agent repository and `.venv` in place. The current `agent.exe` is a
Python-backed installed launcher, not a standalone binary release.

## 2. Define paths

Paste this block into every terminal you use for the workflow:

```powershell
$penaliteAgentExe = 'C:\Projects\New folder\migration-agent\.venv\Scripts\agent.exe'
$penaliteSource = 'C:\Projects\ISOCEL\Alice\Ember\penalite-frontend'
$penaliteState = 'C:\AgentMigration\penalite-frontend\state'
$penaliteStaging = 'C:\AgentMigration\penalite-frontend\staging'
$penaliteReports = 'C:\AgentMigration\penalite-frontend\reports'

$env:AGENT_STATE_DIR = $penaliteState
$env:AGENT_STAGING_ROOT = $penaliteStaging
```

Source, state and staging must remain disjoint. The same source path and external
roots must be used by CLI, GUI and any host/MCP client. If you use a disposable
clone for the pilot, change `$penaliteSource` consistently; that clone has its own
bound project identity. No source clone or branch is created by this guide itself.

## 3. Check the launcher and source base

```powershell
& $penaliteAgentExe doctor
git -C $penaliteSource --no-optional-locks -c core.fsmonitor=false status --short
```

Expect `doctor` exit 0 / `status: ok`; `$LASTEXITCODE` shows the exit code immediately
after a command. A clean Git status produces no changed-file entries. Review and
commit intended changes yourself before staging; do not bypass source drift.
Doctor success confirms the agent environment, not this application's migratability
or a provisioned Angular/native validation workspace.

## 4. Generate local discovery reports

```powershell
& $penaliteAgentExe inventory $penaliteSource --output "$penaliteReports\inventory"
```

Inspect `inventory.md` and `inventory.json` in that output directory. This command
does not call a model, install dependencies or change source. The agent-generated
report from the preparation above can also be inspected directly in the workspace.
Confirm the actual feature/pod components, routes/controllers, services, mixins,
templates, API dependencies and styling that the pilot must preserve.

## 5. Open the project in the GUI

In a separate PowerShell terminal, repeat the path block from step 2, then run:

```powershell
& $penaliteAgentExe ui $penaliteSource --state-dir $penaliteState --staging-root $penaliteStaging
```

Use the browser tab opened by the launcher; it establishes the local session.
Keep that terminal running. Ctrl+C stops the GUI server. Add `--port 8081` if 8080
is occupied. Initially there are no migration records or verified completion in
this new store; that is expected. Starting the GUI does not generate a plan.
Inventory reports alone do not populate tasks. Saved valid plans and workflow
records in the same store will appear through authenticated reconciliation.

Optional `.agent/project-work.json` can describe foundation/modules and link real
workflow IDs. Its creation is an explicit Git setup change; review/commit it before
staging. Declarations cannot count as verified completion.

## 6. Prepare a real plan using approved reasoning

Use a provider approved for this repository, or your authorized IDE/MCP host.
Standalone model-assisted analysis/planning can disclose bounded project material
to that provider. Provision credentials securely through the selected SDK; do not
paste keys into commands, reports or project files. The preparation in this guide
has made no provider request.

For standalone CLI reasoning, choose the non-secret provider/model identifiers:

```powershell
$penaliteProvider = Read-Host 'Approved provider: gemini or openai'
$penaliteModel = Read-Host 'Approved model identifier'

& $penaliteAgentExe analyze $penaliteSource `
  --provider $penaliteProvider --model $penaliteModel `
  --output "$penaliteReports\analysis"

& $penaliteAgentExe plan create $penaliteSource `
  --inventory "$penaliteReports\inventory\inventory.json" `
  --analysis "$penaliteReports\analysis\analysis.json" `
  --provider $penaliteProvider --model $penaliteModel `
  --output "$penaliteReports\planning" --state-dir $penaliteState
```

Check each command succeeds before running the next. Save the actual `plan_id`
from successful output and inspect it:

```powershell
$penalitePlanId = Read-Host 'Plan ID returned by the successful planning command'
& $penaliteAgentExe plan show $penalitePlanId --state-dir $penaliteState
```

`--output` keeps planning governance/plan exports outside the source during this
initial assessment; plans still carry the inspected source identity in SQLite.
Review the policy binding before execution, especially if source governance is
later introduced or customized. CLI `--dry-run` planning alone does not suppress
governance/export writes; an external output location is deliberate here.

Treat a model plan as a proposal. A valid structural plan does not prove the
transformer can convert its files or preserve business behavior. Keep the first
pilot small with explicit behavioral acceptance criteria and dependencies.
Fake-runtime output is only simulation and cannot establish migration success.

## 7. Resolve execution readiness before staging this application

This is the current stop point for automated migration of the actual feature code.
The following implementation/configuration needs to be settled:

1. Extend and verify Ember discovery/transformation for
   `app/features/components/**/component.js` with sibling `template.hbs`, nested
   feature structure and the project's real imports/inheritance/mixins.
2. Establish supported conversion contracts for Ember services, routes/controllers,
   helpers, models and business behavior required by the chosen pilot. The current
   narrow renderer is not a complete Ember application converter.
3. Establish a runnable Angular target foundation and its relationship to the
   original repository. Generating component files does not itself replace the
   Ember package, router, build configuration, dependencies or corporate add-ons.
4. Provision approved Angular validation tools/dependencies externally and a local
   browser coverage/review plan with synthetic data. Use target-only lint/typecheck/
   test/build commands; the Ember deployment/publishing scripts are inappropriate
   for validation. Capture expected behavior for authentication, backend contracts,
   localization and business calculations rather than inferring parity from a build.

Simply relocating source pods or forcing a plan would not preserve their behavior.
`UNSUPPORTED_PREVIEW` or an empty transformation is a stop condition, not successful
migration. Neither `--skip-validation` nor fake checks make changes eligible for apply.

## 8. Guarded execution sequence after readiness is implemented

These are the later commands, not a claim that the current repository can already
complete them. Use actual plan/step/ChangeSet IDs; choose one supported pilot step.
With the common path/environment block active:

```powershell
$penaliteStepId = Read-Host 'Supported pilot step ID from the reviewed plan'

& $penaliteAgentExe stage $penaliteSource --plan $penalitePlanId --step $penaliteStepId `
  --state-dir $penaliteState --staging-root $penaliteStaging
```

Inspect the staged artifact and diff in the GUI. Configure native mode/toolchain/
dependencies/browser plan as described in [native validation](native-validation.md)
before authorizing execution. Then perform the human action in your terminal:

```powershell
& $penaliteAgentExe validation authorize $penaliteStepId `
  --project-root $penaliteSource --plan $penalitePlanId --repair-budget 3 `
  --state-dir $penaliteState --staging-root $penaliteStaging

& $penaliteAgentExe validate $penaliteSource --plan $penalitePlanId --step $penaliteStepId `
  --state-dir $penaliteState --staging-root $penaliteStaging
```

Required [browser capture and AI review](browser-ui-ux-validation.md) must also pass.
In host mode use `validation browser-request` and `validation browser-submit` with
an actual complete review of captured images, then rerun validation. Repairs create
new artifacts and require new checks/capture/review. Provisioned provider review
requires separate explicit disclosure opt-in. Optional enabled E2E runs last.

Only after all required evidence passes:

```powershell
& $penaliteAgentExe review $penaliteStepId --project-root $penaliteSource --plan $penalitePlanId `
  --state-dir $penaliteState --staging-root $penaliteStaging

& $penaliteAgentExe approve $penaliteStepId --project-root $penaliteSource --plan $penalitePlanId `
  --state-dir $penaliteState --staging-root $penaliteStaging

$penaliteChangeSetId = Read-Host 'Exact reviewed and approved ChangeSet ID'
& $penaliteAgentExe apply $penaliteSource --plan $penalitePlanId --changeset $penaliteChangeSetId `
  --state-dir $penaliteState --staging-root $penaliteStaging
```

Execution consent and exact target-artifact approval are separate human actions. Complete
their confirmations yourself; the agent cannot approve on your behalf. Guarded
apply publishes the approved changes only to the separate target selected in
Settings; source bytes remain unchanged. Publish a validated foundation before
functional tasks, then use cumulative target state for subsequent steps. Review
and commit the target result using the agreed delivery procedure. Recovery
or uncertain rollback requires explicit human follow-up, never automatic retry.

The current [governed migration workflow](migration-workflow.md) supersedes the
historical prerequisite/discovery claims above. Pod discovery is implemented;
unsupported semantics use a grounded implementation proposal or an adapter
extension. Actual application parity has not been established by this guide.

See [shared workflow](phase-16-client-setup.md),
[manual GUI acceptance](manual-gui-testing.md) and
[optional project hierarchy](project-work.md).
