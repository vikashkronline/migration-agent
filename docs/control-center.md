# Local Control Center

The Control Center now serves an offline Angular application over canonical CLI/MCP
workflow state. It provides a common project explorer and inspection boundary;
the current workflow adapter supplies migration records. An optional typed
[Git-owned project-work definition](project-work.md) adds foundation/module groups,
owners and acceptance criteria linked to those records. Illustrative wireframe
modules are not invented production records.

## Start and select state

```text
uv run agent ui /path/to/project
uv run agent ui /path/to/project --state-dir /outside/project/state --staging-root /outside/project/staging
```

Use the same external state and staging directories as the CLI/MCP workflow.
Otherwise an empty explorer correctly means no records in the selected store.
Overlapping project/state/staging roots are rejected before serving. Inspecting
the project does not write to its source files.

The launcher binds to loopback, opens the browser with a per-launch credential in
the URL fragment, and prints only the base URL. The client removes the credential
from browser history and obtains a session cookie. Reload and direct navigation
then work within that browser session. Credentials are not persisted in local
storage or printed to stdout. `--no-open` is intended for automation or a trusted
launcher that supplies its own session credential; the printed base URL alone
does not authenticate a new browser. Avoid putting real credentials in shell
history; normal interactive use needs no `--token` option.

`AGENT_STATE_DIR`, `AGENT_STAGING_ROOT`, `AGENT_TRUST_ROOT`, existing launcher
read/workflow capability settings and validation configuration remain effective.
Browser commands cannot change those grants or select another repository.

## Explorer and progress

- Desktop has a persistent explorer. Mobile has a closed-by-default modal drawer,
  opened by **Project navigation**. Selection closes it and focuses the content.
  Close, backdrop and Escape return focus; resizing removes obsolete modal state.
- Foundation, work and knowledge are separate destinations. Foundation remains
  unknown without linked workflow evidence; declared completion is not verified
  completion. Platform health
  reports runtime/Control API diagnostics, not foundation completion.
- Existing plans own their actual tasks and declared dependencies. Selection and
  expansion are separate. Counts cover recorded tasks, including unloaded tasks;
  verified completion requires the guarded apply postconditions.
- Search and Attention query the project rather than only loaded branches. Search
  preserves ancestors and offers additional bounded pages. Attention currently
  covers validation failure, required review/approval, base drift and recovery.
- Task sections show summary/dependencies, recorded workflow milestones, required
  checks, proposed files, operation diagnostics and exact decision bindings.
  Runs offers paged task/run context. Empty and unavailable evidence stays explicit.
- Ask answers bounded questions using selected recorded facts and citations, with
  the same project/revision checks as details. Unavailable information stays explicit.
  For provider reasoning, it displays a scoped CLI argument handoff; it does not
  send browser questions or repository data to a model provider.

Updates use authenticated polling of a project-scoped durable journal cursor and
snapshot revision. SQLite transaction triggers observe CLI/MCP changes; reference
content and project-work definition changes also invalidate the revision. Reconciliation preserves the
selected item and expansion. Disconnection disables commands and labels the
snapshot as unavailable/stale. The process-local legacy broadcaster is not the
workbench's authority or transport.

URLs identify the bound project, stable item and section; available run and artifact
digests are retained. A missing project/item or changed pinned artifact produces
an explicit unavailable state. Selecting the item again requests current evidence.
An open action confirmation closes when its selected detail is refreshed or changed.
Superseded detail responses cannot replace the current selection.

## Review and execution

Review is intentionally read-only. In Artifacts, **Open read-only diff** loads a
changed-file viewer with searchable file navigation, numbered unified/split views,
basic syntax colouring and three-line context hunks. Mobile uses unified view.
The viewer compares the recorded Git base blob with the exact proposed bytes;
current working-tree files are never substituted for that base.
The guarded staging workflow requires a clean Git base; this viewer does not
claim a historical snapshot of uncommitted source edits. Git checkout
conversion can differ from stored blob line endings; changed lines show LF/CRLF
markers and unterminated lines are explicit. The operation and proposed file mode
remain visible even when there are no textual changes.

Each file is fetched on demand through a project/node/revision/artifact/index
reference, never a browser-supplied path. Missing base objects, unsupported modes,
renames, binary/non-UTF-8 or protected contents and oversized previews show an
unavailable state. Limits are 32 KiB per side and 4,000 combined lines; previews
are not silently truncated. The existing bounded proposed-content preview remains
available separately. Superseded requests are cancelled and artifact changes
invalidate the selected review context.

Decision shows ChangeSet, base,
policy and validation bindings plus a structured argument list for the installed
human-terminal approval command. Comments, editing, review submission and full
repository inspection remain in your IDE/CLI. Opening or reading a diff records
no approval. Do not paste the JSON argument array as shell code.

Approval remains a separate human action through `agent approve`; policy-required
Mode A signing remains in that trusted path. There is no browser approval/signing
endpoint. Stage, validate and separately requested exact apply call the existing
guarded runtime. Server authorization, freshness, artifact identity, execution
consent, approval, source drift and recovery checks apply again at execution.
The UI confirmation grants no missing authority. A retry with the same request
identity returns the durable receipt rather than executing twice.

Native validation consent, browser review/repair and provider-disclosure opt-in
remain the existing CLI/host workflows. Their recorded results and operation
diagnostics are inspectable here; this GUI does not introduce additional consent
or repair tools. Recovery offers inspection and human follow-up, never automatic
apply retry. See [native validation](native-validation.md) and
[browser evidence](browser-ui-ux-validation.md).

PNG evidence loads on demand using an authenticated task/revision/index reference.
The server verifies scope, confinement, size, file identity and exact recorded hash;
the browser cannot supply a filesystem path. Architecture diagrams render on demand
with strict Mermaid settings, HTML labels disabled and interactive/configuration
directives rejected. The SVG is displayed as an image, never injected as document
HTML or assigned executable callbacks. Source text remains available.

## Build and tests

The checked-in production files under `src/migration_agent/ui/static` ship with
the Python package, so installed users do not need npm or a CDN. Developers use:

```text
cd ui/control-center
npm ci --ignore-scripts --no-audit --no-fund
npm run lint
npm run format:check
npm test
npm run build
npm run test:e2e
```

The lockfile pins the resolved Angular 21.2, TypeScript 5.9, Bootstrap 5.3 and
Mermaid dependencies. Angular's [compatibility table](https://angular.dev/reference/versions)
requires TypeScript 5.9 through below 6 and the declared Node ranges for Angular 21.
This implementation was built with Node 20.19.2. Angular 21 is currently listed as
LTS in the [release schedule](https://angular.dev/reference/releases); recheck support
when upgrading. The build retains Mermaid's CommonJS optimization warnings;
diagrams are lazy chunks, not initial-load payloads. No `unsafe-eval`, inline
executable handlers, CDN or bootstrap JavaScript plugins are required.

Browser tests use installed Chrome/Chromium and `playwright-core`, without network
or provider credentials. Set `CHROME_BIN` if needed. `npm test` runs Angular
component, routing, HTTP and state tests. `npm run test:e2e` exercises the real
production bundle against offline typed fixtures, including bounded 1,000-task paging,
selection races, artifact invalidation and responsive interactions. The Python
suite additionally launches the actual loopback server and canonical store; that
browser case skips if its optional local tooling is absent. CI/release acceptance
must install the tooling to run it, not interpret a skip as browser acceptance.

The [frontend development guide](../ui/control-center/README.md) describes lazy
feature routes, the route-scoped signal store, reusable components, zoneless
change detection, error boundaries and the loopback development proxy. Production
uses the directly served bundle. Plain CSS and Bootstrap utilities cover current
styling needs without adding SCSS.

## Current limits

This is the implemented common GUI with optional declared project work. It does
not infer technical readiness from discovered code or treat declarations as
verified evidence. The neutral `WorkSourcePort` remains the integration seam for
other workflow adapters. Definition editing and provider-backed reasoning use
existing Git/CLI/host workflows. There is no embedded full code-review editor or
native GUI approval flow. Knowledge is a bounded preview of up to 100 eligible Markdown/Mermaid
references in the declared governance/architecture directories. Deep links pin an
artifact for invalidation, not archival retrieval of all superseded versions.

Measured Windows Chromium checks do not establish full screen-reader/WCAG
certification, all browsers, live Linux execution or binary-sidecar distribution.
Those are not claimed by this implementation. See the
[implementation report](../plannings/control-center-implementation-report.md).
