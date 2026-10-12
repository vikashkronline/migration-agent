# Starting a project for manual GUI testing on Windows

## Package status

The current verified artifact is `dist/migration_agent-0.1.0-py3-none-any.whl`,
which includes the compiled offline GUI. There is no built/accepted standalone
`agent.exe` release in `dist` yet. Packaging helpers exist; standalone distribution
is still a separate release task.

The existing development installation does have
`C:\Projects\New folder\migration-agent\.venv\Scripts\agent.exe`.
Its `doctor`, `ui`, `init` and `adopt` entry points were checked. This is a
Python-backed console launcher; keep the virtual environment and repository in
place. Copying this executable alone will not create a standalone installation.
It can be launched directly from PowerShell without `uv run`.

The commands below also describe the CLI flow for a future accepted executable
release by changing `$testAgentExe` to its installed path. That release is not
claimed to have been tested here.

## Choose your project and external storage

Use a disposable project or clone for your initial testing. These examples create
a new empty project at `C:\AgentManualTest\source`; change it to your chosen source
directory when adopting an existing application. Keep installation, source, state,
staging and any provisioned validation toolchain/dependencies distinct.

```powershell
$testAgentExe = 'C:\Projects\New folder\migration-agent\.venv\Scripts\agent.exe'
$testProjectRoot = 'C:\AgentManualTest\source'
$testStateRoot = 'C:\AgentManualTest\state'
$testStagingRoot = 'C:\AgentManualTest\staging'

& $testAgentExe doctor
```

Expect exit 0 and `status: ok`. The browser GUI needs no provider API key, Docker
or target validation toolchain for ordinary inspection. Git is needed for workflow
base checks and exact diffs. Actual native/container validation has additional
provisioning and human-consent requirements described below.

## Initialize a new project, or adopt an existing one

For a new project:

```powershell
& $testAgentExe init $testProjectRoot
git -C $testProjectRoot init
git -C $testProjectRoot add .agent
git -C $testProjectRoot commit -m 'Initialize agent project governance'
```

Configure your normal Git author identity if Git requests it. `agent init` creates
the directory and agent governance; it does not create a Git repository or scaffold
an Angular/application project. Add your application through its normal development
workflow when needed.

For an existing clean Git application repository, use this alternative:

```powershell
& $testAgentExe adopt $testProjectRoot
git -C $testProjectRoot status --short
```

Adoption inspects application code and creates `.agent` governance and architecture
documentation, normally under `docs/architecture`. Review those generated files
and commit the intended setup changes before staging migration work. Avoid
`--allow-dirty` for your initial acceptance run. Plain GUI inspection can also open
an existing directory without adoption; adoption adds project governance, not
recorded migration progress.

## Launch the GUI

```powershell
& $testAgentExe ui $testProjectRoot --state-dir $testStateRoot --staging-root $testStagingRoot
```

The launcher opens your default browser on loopback, normally
`http://127.0.0.1:8080`, using an authenticated per-launch link. Keep the terminal
running; stop the server with Ctrl+C when finished. Use the automatically opened
tab initially: typing the printed base URL alone in a new browser does not establish
the session. The browser removes the credential from its history. If port 8080 is
occupied, add `--port 8081`. GUI assets are bundled; users need no npm/CDN to view it.

Use the **same external state and staging paths** in every CLI/MCP session and GUI
launch for this project. Different stores can correctly produce an empty explorer.
Environment alternatives are `AGENT_STATE_DIR` and `AGENT_STAGING_ROOT`; explicit
command flags take precedence.

## Populate and inspect progress

A new project initially has no workflow runs or verified completion. That is
expected. Optionally maintain [.agent/project-work.json](project-work.md) to add
your foundation/module hierarchy, ownership, criteria and planning dependencies.
Review/commit definitions before staging; declared completion does not become
verified completion without linked workflow evidence.

Use the existing [standalone workflow](phase-16-client-setup.md#shared-standalone-workflow)
to create and operate actual supported migration records. Planning commands and
all later steps must use the same external store. Once a supported step is staged,
Artifacts can display its recorded files and read-only base/proposal diff.
Opening the GUI alone does not start analysis, generate a plan or run a migration.
Offline `--fake-runtime` planning is useful only for synthetic inspection exercises;
it cannot establish successful validation or authorize source apply.

For end-to-end Windows migration testing, follow
[native validation setup](native-validation.md): provision the approved tools and
dependencies outside the project, explicitly choose native mode, authorize execution
in your own terminal, then validate. Required browser review evidence and separate
human source approval still apply. The default unconfigured restricted mode cannot
execute code or make an artifact eligible for apply. GUI/CLI inspection remains
available while execution is blocked.

## Initial manual acceptance checks

1. Open overview, foundation, modules and knowledge; check truthful empty/unknown
   states and separation of platform health from project completion.
2. Search, expand/select independently, follow dependencies, and use browser
   back/forward/reload without losing the selected context.
3. At mobile width, test the closed navigation drawer, selection, Escape/backdrop,
   focus return and unobstructed content.
4. With staged evidence, inspect checks, artifacts, exact diff and Decision. Try
   unified/split layouts, file search, long labels, light/dark mode and unavailable
   previews. Source files must stay unchanged during inspection.
5. Refresh after an external workflow change and confirm exact artifact links
   invalidate visibly. Missing authority, consent or evidence must keep actions
   unavailable. Human approval remains in your terminal.

Record findings with project/item, run/ChangeSet digest, page, viewport, expected
behavior and actual behavior. GUI developer comments and **Request changes** are
[deferred to a later stage](../plannings/control-center-tree-ux-wireframe-plan.md#later-stage--developer-feedback-and-request-changes);
use your IDE/chat to provide feedback during current manual testing.
