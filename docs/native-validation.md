# Native validation operations

The platform supports `restricted`, `native`, and `container` validation. CLI,
MCP and Control Center use the shared staged workflow and exact approval gate.
For separate migrations, approved changes publish to the cumulative target;
the source stays read-only. See [the migration workflow](migration-workflow.md).

## Select and provision

Set these in the trusted launcher or operator terminal, then restart the MCP
server. Setup previews copy only these non-secret configuration values; they do
not grant execution consent.

```powershell
$env:AGENT_VALIDATION_MODE = 'native'
$env:AGENT_NATIVE_TOOLCHAIN_ROOT = 'C:\AgentTools\node-toolchain'
$env:AGENT_NATIVE_DEPENDENCIES_ROOT = 'C:\AgentTools\approved-node-modules'
# Optional installed Chrome/Chromium for the fixed headless test template:
$env:AGENT_NATIVE_BROWSER_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Prepare these directories yourself through your trusted provisioning process.
The agent does not install packages, run installation lifecycle scripts, fetch
dependencies, or download toolchains. The toolchain layout is:

```text
node-toolchain/
  node.exe                          # Windows; Linux uses bin/node
  node_modules/npm/bin/npm-cli.js
  node_modules/typescript/bin/tsc
  node_modules/@angular/cli/bin/ng.js
  node_modules/...                  # Supporting modules for those installed CLIs
```

The dependencies directory is the approved **contents** of `node_modules`, not
its parent. It is copied into each staged workspace before validation and hashed
before and after execution. Executables, entry points, supporting modules,
dependency contents, and any configured browser are bound to consent. Directories
must be separate from source, staging, state and trust; links/junctions and
credential files are rejected. On Linux, prepare actual regular files instead of
symlinks, and install the agent/Python outside the selected source repository.

Run native validation in a standard user session. Elevated Windows sessions and
Linux root are rejected. Missing tools/dependencies cause an actionable failure;
the agent never changes execution backend as a fallback. The runtime does not
probe Docker or WSL in explicitly selected native mode.

No explicit mode plus a configured image retains container compatibility.
No explicit mode and no image selects restricted mode, which cannot execute code
or authorize apply. Explicit native ignores a leftover image setting. Container
mode still needs a locally installed digest-pinned image and Docker.

## Human consent, validation, repair and apply

Use identical external roots and launcher configuration in every command/client.
Start from a clean Git source and a saved grounded plan:

```text
agent stage <source> --plan <plan-id> --step <step-id> --state-dir <state> --staging-root <staging>
agent validation authorize <step-id> --project-root <source> --plan <plan-id> --repair-budget 3 --state-dir <state> --staging-root <staging>
agent validate <source> --plan <plan-id> --step <step-id> --state-dir <state> --staging-root <staging>
agent validation repair <step-id> --project-root <source> --plan <plan-id> --max-repairs 3 --state-dir <state> --staging-root <staging>
agent review <step-id> --project-root <source> --plan <plan-id> --state-dir <state> --staging-root <staging>
agent approve <step-id> --project-root <source> --plan <plan-id> --state-dir <state> --staging-root <staging>
agent apply <source> --plan <plan-id> --changeset <changeset-id> --state-dir <state> --staging-root <staging>
```

`authorize` requires an actual interactive human console and an exact `EXECUTE`
digest confirmation. It displays the staged diff, fixed templates, identities,
scope and bounded repair allowance. It cannot be piped or automatically signed
by a model. `--profile TYPECHECK` can narrow consent to one catalog profile;
subsequent validation must select that same allowed profile. Planned profiles
must all pass before source review can succeed.

The signed foundation selects a finite validation catalog. The current Angular 21
catalog uses `npm run lint`, `tsc --noEmit`,
`ng test --watch=false --coverage=false`, and `ng build`.
The legacy `node-v1` catalog uses the ChromeHeadless npm test command; the
`node-vitest-v1` compatibility catalog uses its registered Vitest command.
Do not substitute a legacy test command for the selected foundation's catalog.
Node and verified JavaScript entry points are launched directly, never a top-level
`.cmd`/`.bat` or raw shell body. Explicitly trusted npm scripts can themselves
invoke shells. Generated code and allowed repairs are part of the trust decision.

Consent lasts at most one hour and requires at least Mode B. Mode A policies use
the existing external authority/SSH signing boundary; pass `--trust-root` and
`--key-fingerprint` to `authorize`, just as for `approve`. No private keys or
reusable bearer secrets are stored. Mode B trusts the operator's OS account and
external state; it does not protect against arbitrary same-account processes.

`validation repair` resumes an already staged saved step through the shared
deterministic repair loop. Add `--provider-guidance` to use the configured standalone
provider for typed diagnostic guidance. Each accepted repair creates a fresh
ChangeSet and stage, requires new passing validation, and still requires fresh
exact source approval. It consumes the consent's distinct repair allowance;
rechecking the same ChangeSet does not consume another repair. Script, configuration,
dependency, toolchain, expanded scope, policy or base changes require new consent.

For host-assisted repairs use the existing typed MCP repair proposal tool, then
restage/revalidate. A live standalone `migrate` can initially stop for native
consent; retain its saved plan/step, authorize that staged step, and resume through
the saved-step commands above. It cannot authorize execution or publication itself.

External-governance migrations publish into a separate configured cumulative
target, preserving source bytes. Consent binds the exact target snapshot. Team
operators enroll a public signing key and provide Mode A consent for independent
developers; Mode B remains within one local OS account. Dependency copying renews
consent/access checks at bounded checkpoints (64 files or one second) and checks
again after copying and before executing. Full dependency digests remain verified.
See [the current workflow](migration-workflow.md).

```text
agent validation status --project-root <source> --state-dir <state> --staging-root <staging>
agent validation revoke <consent-id> --project-root <source> --state-dir <state> --staging-root <staging>
```

Revocation is transactional and remains available while a worker holds its lease.
The next heartbeat stops the supervised process tree. Revoked/expired consent
also blocks new source review/apply, including previously recorded approval.
Historical execution evidence is preserved.
Renewing consent on an already passed/reviewed step replaces the active consent
and requires revalidation and fresh source approval. It does not relabel the old
execution evidence. Mode A native signatures use their own execution namespace.

## Controls and limits

Native execution has the filesystem and network permissions of the local account.
It is **not a security sandbox**. Positive environment filtering, fresh external
home/temp/cache directories, offline flags and process supervision do not provide
kernel filesystem or egress confinement. Policies requiring container execution,
denied execution, native filesystem isolation, or native network denial fail closed.
Linux also rejects requested hard resource limits it does not implement.

Windows processes enter a non-breakaway Job Object atomically at creation, with
kill-on-last-handle-close. The job enforces 128 processes, 512 MiB aggregate memory
and 60 seconds aggregate user CPU time. Each command has a 60-second elapsed deadline
and 64 KiB retained diagnostics. Timeout, cancellation, lease loss, consent
revocation, normal exit and supervisor crash terminate supervised descendants.
Unverified cleanup cannot produce passing evidence. This covers job descendants,
not arbitrary services a fully trusted account can ask the OS to create.

Linux uses a separate process-group guardian with parent pipe EOF detection and
subreaper cleanup. It has different guarantees; it does not enforce Windows job
limits or prevent explicitly trusted code escaping its group. Strict isolation
must use the container backend. Linux execution acceptance is recorded separately.

Approved output directories are `.angular`, `coverage`, and `dist` in staging.
Changesets cannot target them or `node_modules`. Other input mutations fail
validation. Configure project build/test outputs accordingly. Source base and
staged inputs are rechecked; drift blocks apply and is never silently overwritten.

Version 2 immutable validation records bind backend, full execution policy,
consent, catalog/environment policy, actual adapter limits, tool/dependency
identities, inputs and cleanup. Source approval binds that exact execution digest.
Ordinary reports, fake runners and version 1 evidence cannot authorize new apply.
Revalidate an existing staged step; revalidation clears its prior approval. If
base/project policy has changed, create a fresh grounded plan instead. Old records
and hashes are preserved as history.
Legacy `validate` without plan/step and `run`/`run resume` support fake reports only;
live commands must use the shared staged workflow. They cannot bypass restricted
mode or native execution consent merely by declining to create apply evidence.

Automated disposable fixtures and measured process tests are implementation
evidence. They are not live IDE sessions, operator signing, a real Angular project
acceptance run, real Docker acceptance or Linux execution proof. See the smoke
checklists for those remaining acceptance journeys.

## Browser gate amendment

Command checks alone no longer authorize production source apply. Configure the
[browser UI/UX gate](browser-ui-ux-validation.md) before native consent, then use
all command profiles and complete the AI screenshot review. The browser plan and
fixed worker participate in consent; renewal requires fresh browser capture.
Narrow command-profile reports cannot satisfy browser approval. Container mode
supports the fixed worker in a provisioned pinned image without backend fallback.
