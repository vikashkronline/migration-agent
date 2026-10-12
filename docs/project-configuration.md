# Project configuration and Settings

Configuration management is available through **Control Center → Settings**, `agent config`,
and bounded MCP tools. Saving configuration never starts a migration, installs dependencies,
grants execution consent, signs an approval, or changes the source repository.

## Scopes and precedence

| Scope | Examples | Storage and authority |
| --- | --- | --- |
| Shared project | Approved provider/model profiles and data purposes; default profile; turn/file limits; allowed validation modes; browser export; supported target preset | Owner-signed `.agent/config.json` in external governance |
| Personal workstation | Allowed model choice and smaller turn budget; installed toolchain/dependency/browser paths; coverage-plan path; pinned image; proposed next-launch directories | External principal/project-scoped preferences; `AGENT_LOCAL_CONFIG_ROOT` selects the preferences root |
| Launcher | Explicit CLI/environment provider, model, execution mode and installed paths | Shown with launcher provenance; constrained by signed project settings |
| Bound directories | Current source, governance, operational state, staging and external trust | Read-only in the running session; explicit startup/setup handoff |

Shared constraints apply first. An explicit launcher value remains effective until restart.
The GUI shows effective values, their origins, diagnostics, and timing separately from edited drafts.
Source and governance identity are never hot-rebound. A new state root starts a separate operational
history; old state, artifacts and approvals stay at their original locations. Staging changes require
fresh staging/validation when previous artifacts no longer belong to the selected root.

The final target directory selects the separate cumulative publication workspace.
New staged artifacts, validation, consent and exact approvals bind its root and base fingerprint.
Selecting or changing it requires fresh artifacts; an existing approval cannot be reinterpreted
against another directory. External governance, source, staging, state and trust remain separate.
See the [migration workflow](migration-workflow.md) for foundation and publication prerequisites.

## Eligible users

| Action | Required project capabilities |
| --- | --- |
| Inspect Settings | `project.read`, `configuration.read` |
| Save a shared candidate | `configuration.propose`, plus inspection |
| Save personal choices | `configuration.local.write`, plus inspection |
| Change personal provider/model choice | Personal write and `provider.use` |
| Change execution/environment/root choices | Personal write, `validation.run`, human `execution.consent` |
| Prepare/activate shared settings | Owner membership, `rules.manage`, human `access.commit` |
| Provider connectivity probe | Inspection and `provider.use`; active profile permits connectivity |
| Installed-tool probe | Inspection, `validation.run`, human `execution.consent` |

New capability names do not expand existing signed roles. An existing owner must use the existing
Users and access / `agent access role-set` proposal and signature workflow to adopt the relevant
capabilities. Newly bootstrapped role templates include the finite configuration capabilities.
Git developer/maintainer membership alone grants none of these permissions.

A custom configuration reader can open Settings without plan/run permissions. Its session bootstrap
does not fetch workflow trees or start event streams. Direct API requests still receive fresh checks.

## Owner setup and routine changes

1. Open **Models** and propose a named profile with an installed provider, allowed model identifiers,
   an included default, and explicit data purposes. The supported endpoints are fixed Google Gemini
   and OpenAI endpoints. Arbitrary endpoints, credentials, account OAuth and provider discovery are
   unavailable.
2. Review the candidate, field checks and operational impact. **Save shared proposal** records a draft
   in external state; active governance stays unchanged.
3. An owner chooses **Prepare owner approval handoff** and reviews the exact candidate in a trusted
   terminal. The displayed `agent config approve` argument list includes the source, proposal ID,
   state, staging, trust and preference roots. The CLI requires interactive confirmation and genuine
   signing authority. The browser cannot create this signature.
4. After activation, refresh Settings. Ordinary permitted personal choices use **Save my selection**
   and require no owner signing ceremony. They apply to the next operation.

Shared settings use the existing signed access/rules revision and invalidate prior access contexts.
Owner review binds the exact candidate bytes, previous file digest, source revision, project binding,
nonce, lifetime and future protected-file hash. Activation records a trusted intent and coherently
updates the file, trust anchor and active pointer. No unsigned active configuration is written first.

Historical proposals remain readable. **Restore as draft** copies old values into a new candidate
against the current context; it does not rewind signed history or reuse a nonce. History labels active,
stale and draft candidates. A stale proposal must be restored and reviewed before signing.

## Checks and recovery

**Check my configuration** runs offline schema, profile, policy, architecture and path checks.
Errors block saving; prerequisite diagnostics guide toolchain, execution-consent or coverage setup.
These checks do not certify a project build or replace workflow validation evidence.

Provider/tool checks require explicit confirmation. A provider probe sends a fixed connectivity
request with no source, diff, image or repository content. It uses a fixed endpoint, short timeout,
bounded response and bounded retry policy. The toolchain probe runs the selected installed Node
binary with fixed version arguments under process supervision; it executes no repository script.
No probe installs software or generates a raw shell command.

Checks use the existing durable operation store, immutable input, principal/access binding, leases
and bounded capacity. The UI polls their status and supports cancellation/recovery. A terminal
receipt is replayed without another probe. An interrupted in-flight provider call becomes
`RECOVERY_REQUIRED`; account usage must be reviewed before explicitly starting a new check.

If a save/check response is lost, **Recover same request** reuses the exact request ID, revision,
configuration and check kind. Edits are retained on conflicts. New writes are disabled on a stale
or disconnected view. Unsaved edits trigger a navigation confirmation. Check results from older
revisions are labelled as historical.

An interrupted signed activation blocks ordinary reads with `ACCESS_ACTIVATION_PENDING`. Complete
the verified intent through the trusted terminal:

```text
agent config recover SOURCE --state-dir STATE --staging-root STAGING --trust-root TRUST --local-config-root PREFERENCES
```

For a recorded check, add `--check OPERATION_ID`. Recovery does not create new authority or reset
trust. A lost activation receipt can be recovered from the exact verified active revision without a
second signature or activation.

## CLI and MCP

Run `agent config --help` for `show`, `schema`, `propose`, `local-set`, `review`, `approve`, `history`,
`check`, `check-status`, `recover` and `restore`. CLI candidates use bounded, strict public JSON models.
Unknown fields, duplicate keys, unsupported schemas, secret-shaped values and unsafe roots are rejected.
The recognized legacy empty configuration is preserved until deliberate typed adoption; arbitrary
legacy workflow definitions are not silently translated or erased.

MCP exposes `migration_configuration_show`, `migration_configuration_propose`,
`migration_configuration_check` and `migration_configuration_check_status`. The launcher ceiling and
signed project grants both apply. MCP checks are offline only. MCP provides no personal-write,
provider-probe, execution-consent, signing or configuration-activation tool.

Model adapters pin provider/model/turn limits and check approved disclosure purposes before sending
content. Runtime audit events and worker operations record configuration snapshots with provenance.
Workers retain their snapshot; changed authority is checked at execution checkpoints.

## Foundation integration

Target preset constraints must agree with accepted architecture. The Foundation Wizard uses backend
DTOs for actual packages, versions and mappings and permits explicit strategy edits. Unknown packages
must be resolved with installed mappings or explicitly deferred/removed. Changing a draft requires
new ADR confirmation; matching an old preset name cannot reuse an old draft's confirmation.

Foundation staging selects a grounded recorded plan and step and uses the standard durable staging
workflow. It creates no placeholder approval or fake evidence. Source, policy and staged bytes are
rechecked for readiness. A staged foundation remains unvalidated until real workflow validation passes;
the presence of a bootstrap file or three unrelated ADRs does not unlock migration.

Credentials remain managed outside Settings. Native supervision retains the existing execution
consent and platform limitations; saving settings does not grant isolation or execution authority.
