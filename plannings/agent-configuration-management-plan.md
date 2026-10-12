# Agent and project configuration management — implementation plan

Date: 2026-10-12  
Status: Implementation authorized by the subsequent user request on 2026-10-12; see the implementation report  
Scope: Configuration contracts, resolution, RBAC, CLI/API/GUI management, validation, activation and workflow integration

## 1. Objective and completion criteria

Provide one discoverable place where an eligible user can inspect effective settings, understand their origin, edit permitted values, validate a candidate and see when it takes effect. Owners can approve shared/security changes through the existing signed governance path. Users can save ordinary preferences within those approved constraints without repeating an owner-signature ceremony.

The feature is complete when equivalent CLI/API/GUI operations use the same application services; values shown match those actually used by workers; settings cannot bypass authorization, accepted architecture, source protection or execution consent; and missing prerequisites lead to an actionable next step rather than misleading readiness.

The selected source application remains read-only. This work configures the agent platform; any generated application files must continue through the agent's guarded migration workflow.

## 2. Current implementation and prerequisites

Current evidence:

- [Settings](<C:/Projects/New folder/migration-agent/src/migration_agent/config.py:16>) is environment-backed. Provider/model, state/staging/trust, execution and browser settings have no general GUI editor.
- [GUI launcher](<C:/Projects/New folder/migration-agent/src/migration_agent/cli.py:2502>) binds the repository and constructs services at startup. A browser request cannot safely replace those roots by changing a string.
- [Foundation Wizard](<C:/Projects/New folder/migration-agent/ui/control-center/src/app/workbench/wizard/stack-wizard.ts:47>) selects a preset, previews mappings/ADRs and requests staging. Its package matrix currently displays outcomes rather than providing edit controls.
- [Protected configuration](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/access_rules.py:14>) includes the entire `.agent/config.json`. Updating that file requires the signed-rule lifecycle; a new settings API must not write it directly as an ordinary preference.
- [Capability registry](<C:/Projects/New folder/migration-agent/src/migration_agent/domain/access.py:17>) provides finite grants and human-only operations. Roles, Git labels and session tokens are not interchangeable with approval.
- [Execution diagnostics](<C:/Projects/New folder/migration-agent/src/migration_agent/application/doctor.py:32>) distinguish configuration presence from execution readiness. Native consent and browser evidence remain separate requirements.

Two integration issues must be reconciled before settings can claim a secure foundation-ready flow:

1. The current stack acceptance/staging handlers fall back to `project.read` after privileged authorization fails. See [acceptance](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/control_api/server.py:855>) and [staging](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/control_api/server.py:893>). New settings handlers must fail closed; existing wizard mutations must use registered capabilities and the accepted human channel.
2. Stack status uses ADR counts and `src/main.ts` presence, while staging constructs an automatically approved plan. See [status](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/control_api/server.py:735>) and [foundation plan](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/control_api/server.py:965>). Configuration checks must project real workflow evidence and must not inherit that readiness/approval shortcut.

These are integration prerequisites observed in code, despite broader completion statements in phase status. This planning task does not implement their remediation or certify the current wizard's execution path. The [foundation review](foundation-stack-wizard-review-report.md) remains relevant.

## 3. Scope and ownership of configuration

Do not expose a single unrestricted settings dictionary. Define four explicit scopes, and show the scope beside each editable value.

| Scope | Contents | Storage and authority | Change path |
| --- | --- | --- | --- |
| Shared project configuration | Approved runtime profiles, provider/data boundaries, workflow defaults, constraints and policy references | Typed, versioned `.agent/config.json` in the externally bound governance repository; owner-signed protected digests | Draft → validation → exact owner review/signature → guarded activation |
| Local workstation configuration | Non-secret executable/dependency/browser locations, selected environment profile, operational directory selections | OS-user configuration outside source/governance/staging/trust; associated with verified project binding and principal | Eligible user's local save or explicit restart/reconfiguration procedure; real execution still requires consent |
| Session/run choices | Model selection and supported run limits within approved bounds | Operational state; immutable effective snapshot attached to the operation | Authenticated permitted save/select; no shared governance write |
| Personal presentation preferences | Theme, table preferences, default settings tab | Existing per-user UI preference mechanisms; no execution authority | Immediate save without signature |

Local values must never weaken project constraints, change ownership, enable an unapproved provider destination or grant execution/apply authority. Local file permissions and the trusted OS account remain deployment trust boundaries; a JSON digest is not a defense against a workstation administrator replacing the verifier.

Absolute machine paths normally belong in local bindings/profiles, not portable shared defaults. Shared documents reference approved profiles and logical roots. Existing signed bindings contain physical roots; preserve their authority and require explicit reconciliation rather than silently replacing them with a new portable representation.

Do not store credentials, private keys, tokens, signing-agent material, arbitrary environment dumps or provider authorization headers in any scope. The GUI does not accept secret inputs. Authentication continues through the existing external provider/OS mechanisms; display only a bounded availability status, not a credential value.

## 4. Configuration coverage

All controls must come from a versioned field catalog backed by actual adapter capabilities. If a setting is not consumed by the runtime, show it as unsupported/read-only or omit it; never offer a working-looking control that has no effect.

| Section | Cover these values | Editing and validation behavior |
| --- | --- | --- |
| Overview | Project identity, active configuration revision/digest, actor permissions, effective provider/model, paths, execution mode, blockers and pending changes | Read-only summary with links to the relevant editor or existing workflow; distinguish active, draft and restart-pending values |
| Models and providers | Project default profile; allowed provider/destination/model profiles; user's selected allowed model; supported per-run turn/context/output limits | Owners govern allowed profiles and disclosure. Eligible users select within them. Adapter capability checks reject unsupported options; no arbitrary endpoint textbox |
| Project and directories | Read-only source, governance root, staging, state, externally trusted root, proposed final target/output root, package/workspace identity | Paths have distinct labels and lifecycle. Existing source/governance/trust binding cannot be hot-edited. New source means new project setup; final target remains unavailable for apply until destination enforcement exists |
| Target architecture | Accepted target framework/version set, preset, package manager/lock strategy, styling/testing/state decisions, replacement mappings and supported layout choices | Link to and extend the Foundation Wizard's typed draft editor. Show accepted ADRs above defaults. Editing is a proposal; it cannot silently regenerate accepted artifacts |
| Environment and execution | Restricted/native/container selection within policy; installed toolchain paths; external offline dependencies; pinned installed container image; actual supported supervision limits | Local paths need eligible operator permissions; owner controls safety ceilings. Display native execution limitations. Selecting native is not executing or consenting |
| Validation and browser checks | Required adapter-supported compile/build/test profiles; browser binary; route/state/viewport plan; review mode; optional provider export | Required gates cannot be removed by a user preference. Coverage editor uses the existing browser-plan schema. Provider export is owner-controlled and explicitly disclosed |
| Workflow defaults | Supported task file limits, proposal/run budgets, repair budget where supported, approval assurance and expiry constraints | Separate project limits from per-run values. Values are bounded by platform constants and signed policy. Never expose raw command templates as editable shell |
| Governance and access | Effective rules/assurance, owner identities and roles, signed repository connection, publication enforcement status | Summary plus links to Users and access and existing rule/publication review. Do not duplicate user administration or let this screen edit trust anchors |
| History and pending changes | Active and candidate digests, field diff, proposer/approver, validation evidence, effective timing and related operations | Scoped audit view; restores are fresh proposals. Retain superseded versions and immutable run snapshots |

### 4.1 Specific current setting treatment

- `AGENT_RUNTIME_PROVIDER`, `AGENT_RUNTIME_MODEL`: retain compatibility as explicit launcher/session overrides, validate against approved profiles, and show their origin. They must not silently override a provider disclosure boundary.
- `MIGRATION_AGENT_MODEL`: show its legacy status when it supplies the effective model. Provide a migration suggestion without writing shell profiles or environment variables automatically.
- `AGENT_STATE_DIR`, `AGENT_STAGING_ROOT`: show the current launched values and whether they override saved local settings. Changing them requires an idle/restart flow; do not create an empty new store and imply the history disappeared.
- `AGENT_TRUST_ROOT`: display the current verified binding; no normal editable text field. Trust relocation needs an independently trusted administrative procedure.
- `AGENT_VALIDATION_MODE`, image/toolchain/dependency locations: validate policy compatibility and actual backend support. No automatic Docker pull, package installation or tool download.
- Browser binary/plan/review/export settings: configuration is separate from native browser consent, provider export permission and captured/reviewed evidence.
- MCP launcher capability ceilings: show only as administrator-controlled effective ceilings. Browser settings cannot raise them.
- Fixed execution limits and unsupported model sampling parameters remain read-only until their adapters expose validated contracts. Do not invent temperature, streaming, token budgets or timeout sliders solely because another provider offers them.

### 4.2 What “source” and “target” mean in the UI

Use **Source repository — read-only**, **Governance repository**, **Staging workspace root**, **Final target application directory**, **Operational state**, and **External trust**. Avoid the current ambiguous use of “target repository” for the opened source.

For a staged-only migration, the target directory card says **Publication not configured**. It links to the destination setup requirement; it does not claim an ordinary path setting enables final apply. A separate-destination apply implementation must bind destination identity/base and source evidence, validate disjoint roots, and preserve original source hashes before enabling that action.

## 5. Eligibility and RBAC

Authorization is backend-derived and field/action-specific. The following role names describe recommended grants, not hard-coded checks.

| User | Inspect | Propose shared settings | Save own allowed choices | Environment setup | Activate shared/security changes |
| --- | --- | --- | --- | --- | --- |
| Inspection-only/uninitialized | Limited public diagnostics and authorized source summary | No | Presentation preferences only | No | No; show bootstrap prerequisite |
| Viewer | Authorized redacted effective settings | No by default | Presentation preferences only | No | No |
| Developer | Authorized settings and readiness | Yes if explicitly granted | Allowed model/run choices with applicable provider capability | Read; local setup only if delegated | No |
| Reviewer | Settings, candidate diff and check evidence | Only if explicitly granted | Choices within their actual grants | Read | May review architecture under existing knowledge authority; cannot activate owner-only security changes |
| Operator | Settings and execution profiles | If explicitly granted | Allowed operational choices | Local profile setup if granted; separate human execution consent | No unless independently an eligible owner |
| Owner | Authorized complete public configuration | Yes | Allowed local/session choices | Yes within enforced constraints | Exact signed shared/security activation |

Proposed finite additions, to be introduced only in the authorized implementation slice:

- `configuration.read`: read authorized, redacted configuration/proposal/history projections, also requiring `project.read`.
- `configuration.propose`: persist shared configuration candidates; no effective authority.
- `configuration.local.write`: save the current principal's non-secret permitted preferences/environment declarations, with field-specific operational grants.

Do not create a parallel security activation permission. Shared protected-file activation reuses eligible owner checks, `rules.manage`, `access.commit`, signed access revision verification and existing human-only constraints. Users and roles continue through their existing service. Native consent uses `execution.consent`; model calls use `provider.use`; validation uses `validation.run`; architectural draft/acceptance uses registered knowledge capabilities and the accepted human-only review path.

New capabilities require an owner-approved update to existing signed role definitions. Updating the capability catalog or built-in role template must not silently expand an already enrolled user's grants. Absent grants deny; unknown capability names deny; no fallback from a rejected write to `project.read`.

On an existing deployment, an owner can adopt the new grants through the existing
access CLI/Users and access lifecycle; access to the new Settings page must not be
required to perform that adoption. No signed approved runtime profile means
**Owner setup required** for model selection/invocation under the new resolver.
Preserve offline inspection and draft editing; do not make a default provider or
an unsigned environment value into an implicit approved disclosure profile.

Show Settings navigation when configuration read is granted. Inside, show permitted sections and read-only fields with a concise reason, such as **Owner signature required**, **Your role cannot propose this change**, or **Controlled by launcher**. Do not leak inaccessible values through a disabled input, error response or hidden DOM element. Recheck permissions before validation/activation, when replaying receipts and at worker checkpoints. Revocation disables stale actions and does not preserve draft-time rights.

## 6. Placement and UI/UX

### 6.1 Navigation

Add a persistent **Settings** gear link to the project header, alongside Platform health, shared by desktop and mobile. Keep it outside the workflow task tree: settings are project administration, not completion tasks.

Use `/projects/:projectId/settings` with deep-linked sections: `overview`, `models`, `directories`, `environment`, `validation`, `governance`, and `history`. Provide a link to the existing Foundation Wizard for target architecture and to Users and access for membership. Personal preferences are clearly marked **Only for me**; workstation paths say **This workstation**. Do not introduce a multi-project daemon or global administration surface in the first slice.

Add contextual **Configure…** links from Platform health, missing-prerequisite messages, Foundation Wizard and relevant task blockers. Preserve the return location, node/artifact context and project binding when returning to the workflow.

Decouple settings entry from the current full-workbench session fetch. The
[project guard](<C:/Projects/New folder/migration-agent/ui/control-center/src/app/core/routing/project-guard.ts:9>) currently reaches the workbench through `SessionState`;
that projection requires plan/run inspection as well as project access. Supply a
minimal authenticated project/permission projection and load the task explorer
only when authorized. A custom user with configuration read but no plan/run read
must be able to open permitted Settings sections without receiving unrelated
workflow data or needing additional grants.

### 6.2 Layout and controls

Use the existing Angular 21 standalone/OnPush/Signals Control Center, Bootstrap 5.3 utilities, theme, icons and typed HTTP patterns. The migrated target's Angular preset does not determine the GUI's framework version. No new component library or Bootstrap JavaScript behavior is required.

Desktop: section navigation on the left, a focused form on the right. Mobile: an accessible section selector and stacked fields/cards; existing project navigation stays an overlay. Use a full page rather than a modal for long-lived configuration editing and conflict resolution.

Each field shows label, current effective value, scope, source, editability, concise help and validation result. Use selects for supported providers/profiles/enums, bounded numeric controls for supported limits, text path inputs with an explicit **Check path** action, and links for protected bindings. A browser directory-upload control is not a native host folder picker and must not upload a repository or credential files. Native browsing can be added only through a separately authorized, bounded host picker.

Do not show Python class names, fabricated signatures, raw policy JSON or migration implementation details as the user's configuration workflow. Advanced view may show schema version, digest and sanitized provenance for technical review, without becoming an arbitrary JSON editor.

Illustrative arrangement:

```text
Project · Settings                          Current role / synchronized status
Overview       Models and providers                Scope: Only for me
Models         Provider profile   [Approved profile ▼]
Directories    Model              [Compatible model ▼]
Environment    Effective source: local selection; constrained by project revision
Validation     Credentials        Available / Unknown; managed outside this GUI
Governance     [Check configuration] [Test provider connection]
History        Check results and next prerequisite
               [Cancel edits] [Save my selection]
```

For shared edits, the action bar instead offers **Save draft**, **Validate draft**, and **Review owner approval**. The review page displays the exact field/file diff, effects, digest and terminal handoff. Avoid a generic **Apply everything** button.

### 6.3 Save, error and accessibility behavior

- Separate draft, saved preference, active project revision and restart-pending values. Never change the displayed active value optimistically before backend confirmation.
- Keep a dirty indicator and navigation protection for unsaved edits. Drafts resume from the backend with revision checks; do not persist sensitive settings in browser localStorage. **Reset field** explains which inherited value will replace it. **Cancel edits** leaves active configuration intact.
- Model/profile selection suggests compatible dependent values without silently replacing custom choices. Changes that conflict with accepted ADRs show a review link; ordinary edits do not launch the full wizard again.
- Put inline errors beside fields and provide a linked error summary after validation. Use text/icon status as well as color. Preserve keyboard order, focus, labels, screen-reader announcements and mobile touch targets; diff/history views remain usable without horizontal page scrolling.
- A save response lost to timeout is **Outcome unknown**, not **Failed**. Recover the same request ID/receipt before retrying. Retain valid edits after server errors; do not reset the form to defaults.
- Disconnection permits clearly labeled cached inspection and local form editing, but blocks server mutations/checks/activation. Reconnection refreshes active permissions and revision before submission.

## 7. Resolution and effective configuration

Introduce one typed resolver used by CLI, API, MCP and workers. The GUI edits inputs to that resolver, not a separate browser-owned configuration copy.

Resolution proceeds in two stages:

1. Establish non-overridable platform invariants, verified binding, current signed project constraints, accepted architecture and trusted launcher capability ceilings.
2. Resolve defaults and allowed choices: project default → current principal/workstation profile → explicit environment/CLI/session override, only for fields that support override and only inside the constraints from stage 1.

When a requested override is incompatible, return a typed blocking diagnostic. Do not silently select another model/provider or ignore a security-relevant value. For an environment-controlled field, show the variable name and a restart instruction; do not claim a saved GUI preference overrides the running launcher.

Every effective field reports its value, origin, scope, constraint reference and update mode: next operation, idle activation or restart. Defaults remain deterministic and schema-versioned. Existing model aliases and launcher options are supported through an explicit migration/compatibility layer.

A legacy `.agent/config.json` with unknown or conflicting fields is not blindly deserialized into `Settings` and rewritten. Preserve its bytes and diagnose the unsupported schema; provide a bounded reviewed upgrade proposal. Existing projects do not need reinitialization merely to inspect their settings.

## 8. Validation and checks

| Check level | What it proves | Rules |
| --- | --- | --- |
| Form/schema | Required values, field types, bounds, enums, package coordinates and typed plan shapes | Fast client assistance plus identical authoritative server validation; reject unknown fields, duplicate keys and secret-shaped inputs |
| Cross-field/project | Allowed provider/model/options; ADR compatibility; protected limits; source/destination/root relationships | Deterministic and offline; uses the exact active access/config/binding/architecture revisions |
| Filesystem/environment | Selected locations exist as expected; confined files; tool identities; installed dependencies/image/browser prerequisites | Bounded reads through existing inspection adapters, fresh checks against canonical physical paths; no source writes or directory-wide scans by default |
| Optional capability probe | A supported installed tool or provider can answer the stated probe | Explicit user action, current capability/policy checks, fixed argv or typed provider request, bounded duration/output; no repository script execution or automatic data export |
| Workflow validation | Staged artifact actually passes required compile/build/test/browser checks | Existing execution backend, per-step consent and evidence contracts; configuration checks do not replace these gates |

### 8.1 Required detailed checks

- **Models:** provider/model syntax, adapter support, available option ranges, approved endpoint and data class. A cached catalog states its version/age. Unknown models may be saved as an unresolved draft, but model invocation remains blocked pending verification; do not call the provider on every keystroke.
- **Provider test:** opt-in, minimal fixed test payload with no source/diff/images, allowed destination displayed, provider authorization and fresh permissions. Success means connectivity for that probe, not migration quality or unlimited data-export permission. Missing authentication returns setup guidance without reading, storing or echoing credentials.
- **Paths:** normalize according to Windows/Linux semantics; reject unsafe overlaps among source, governance, staging, state, trust and destination, including case, links/junctions and physical aliases. Verify path budgets and repository/root identity. Persist repository-relative artifact paths as POSIX. No shell expansion or path-controlled command execution. Network paths remain unsupported unless a capability explicitly declares safe handling.
- **Write readiness:** do not create a probe marker in the source to test permission. Offline permission checks are only estimates. Actual directory/file creation occurs through the approved confined operation, with real postconditions and typed failure.
- **Tools/dependencies:** installed executables must be outside candidate repository/workflow roots and match the approved profile's identity/digest. Packages, lockfile, runtime/compiler/build/test versions must match a supported matrix; source manifests are evidence, not executable instructions.
- **Execution:** untrusted/default mode remains restricted. Native process supervision is not a security sandbox. Selecting a backend, tool path or checkbox cannot manufacture consent. Container configuration needs a locally installed pinned image; this screen does not pull it silently.
- **Browser:** coverage plan uses valid bounded cases/route/state/viewport definitions. Missing browser/review/E2E evidence remains explicit. Changing review/export destination triggers the relevant signed policy/disclosure review and fresh consent/evidence.
- **Governance:** exact current base/access/config revisions, genuine signatures where required, expiry, unused nonce, eligible owner and current signer possession rules. Recovery verifies trusted intent/history and bounded files; it never repairs trust by accepting the candidate's own authority.

Return structured diagnostics with field path, stable code, severity, evidence reference, and safe next action. Distinguish **Invalid**, **Prerequisite missing**, **Not checked**, **Unsupported**, **Check passed**, and **Stale**. An incomplete draft can be saved; execution/activation requires the applicable checks. Doctor `ok`, accepted ADR count, staged file presence and successful connectivity must not become a single “project ready” flag.

External/provider checks are asynchronous durable operations with bounded aggregate deadlines, cancellation and receipt polling. Client timeout must not silently leave an untracked server task running. Do not introduce a cache/service layer for unrelated Git-directory synchronization as part of this scope.

## 9. End-user workflows

### 9.1 Routine user model selection

Open Settings → Models → select an owner-approved profile/model → run offline checks → save **Only for me** → use on the next authorized model operation. An optional provider test is a separate action. No owner signature is required when no shared constraints, destination or disclosure authority changes.

If the launcher overrides that value, offer **Save for next launch** and show the typed restart arguments. The page must not falsely report a live switch.

### 9.2 Shared project/security change

```mermaid
flowchart LR
  Edit[Edit permitted fields] --> Draft[Save immutable candidate]
  Draft --> Check[Validate and show impact]
  Check --> Review[Review exact diff]
  Review --> Sign[Owner signs in trusted terminal]
  Sign --> Activate[Guarded activation]
  Activate --> Refresh[Refresh effective settings and affected work]
```

The candidate contains concrete file bytes/hashes, current base revisions and impact information before the owner reviews it. The GUI provides complete trusted-terminal arguments. Signing does not use browser tokens or an environment switch. A signed-proof submission API may transport a genuine externally obtained proof; it is not a signing channel.

Use one owner review for a coherent protected configuration change, rather than asking the owner to approve the same fields separately in Settings and Users and access. Config bytes are bound by the proposed signed rules/access revision. Activation validates the exact saved candidate and reports the resulting active digest or restart-pending state.

### 9.3 Environment setup

Choose an allowed backend → declare external toolchain/dependency/browser locations → inspect prerequisites → run separately authorized fixed probes → save a local environment profile → return to the blocked task. The task requests its own exact execution consent and validation. No build or install is implied by saving the profile.

### 9.4 New source, target or root change

- **New source:** provide a setup form that prepares a distinct project initialization request with separate governance, staging, state and destination selections. Use an explicit local setup context supplied by the trusted launcher; an ordinary project token cannot inspect arbitrary unbound repositories. Complete owner bootstrap through its existing trusted process. Open a newly bound session after initialization; preserve the previous project's state.
- **Final target:** propose an explicit destination binding and inspect its existing base/content. Publish only once the destination-aware guarded workflow is implemented and accepted. Until then, keep this setting as a planned destination and explain that staging is available but final publication is not.
- **State/staging change:** require a safe idle/checkpoint boundary, preserve existing artifact/history locations and prepare a restart. Do not move/delete old directories, silently adopt a new store, or reinterpret an old artifact as belonging to the new root.
- **Source/governance/trust relocation:** read-only in normal settings. Provide a trusted administrative handoff for reviewed rebinding; no browser edit or copied JSON can reset the external trust floor.

A signed path proposal is not permission to browse or rewrite unrelated files. Every read/write uses the explicit setup or bound-project scope. Active operations either finish their pinned scope at a safe checkpoint or are cancelled with a recorded outcome before the new binding can take effect.

### 9.5 Target architecture and dependency edits

Settings links into the Foundation Wizard using the current accepted stack revision. Add actual typed mapping edit controls there, with source evidence and behavioral obligations. Do not maintain a second package table in Settings. Accepted ADRs win over defaults; changed presets/mappings generate a diff and new architecture/foundation artifacts where required, preserving human edits. Existing validated application artifacts are never regenerated by merely opening Settings.

### 9.6 Restore or recover

History → select a prior configuration → inspect a new diff against current → validate → appropriate save/sign/activate. Restoring a security setting creates a new signed revision, not rollback of the active pointer or consumed nonces.

Interrupted activation enters a recoverable operational outcome with a durable trusted intent. Show **Recovery required**, block affected execution and link to the exact existing recovery command. No automatic trust reset or partial-success badge.

## 10. Safe persistence, activation and concurrency

Persist drafts/check results/receipts in external operational state; local preferences in the current principal's external user configuration; accepted shared configuration in the external governance repository. Use existing authoritative operation/journal patterns rather than a parallel settings workflow database.

Protected-file activation needs a coherent transaction-like extension of the existing signed governance mechanism:

1. Keep candidate bytes in state and validate them before changing active files.
2. Owner signature binds the future protected-file hashes in the candidate access/rules revision, together with current base, binding, nonce and lifetime.
3. Under the short activation fence, recheck current rights and exact bytes; record a durable trusted intent; update protected content and access pointers coherently with atomic writes and postconditions.
4. Readers observing an incomplete transition fail closed as activation-pending. Recovery verifies both file hashes and signed revision; it finishes or restores only the recorded trusted transition.

Do not write an unsigned active `.agent/config.json` first and leave ordinary operations blocked until the owner later signs it. Do not build a second unsigned configuration pointer that overrides the signed one.

Preserve access coordination → project apply → staging ordering where multiple locks are needed. Configuration reads use verified active snapshots without acquiring the writer fence. Do not hold fences during provider calls, probes, user review or a wait for worker shutdown. Busy apply checkpoints return a bounded retryable conflict; activation must not deadlock with validation.

Each operation records an immutable effective configuration digest plus the relevant provider/execution/architecture/binding provenance. Services and workers consume that snapshot; they must not repeatedly read a mutable global `Settings` object and change behavior mid-run. Recheck current authority and applicable safety constraints at checkpoints. A transport/server restart cannot authorize old requests under a new principal.

| Change | Expected operational effect |
| --- | --- |
| Theme/table preference | No artifact or approval invalidation |
| User's allowed model choice | Next model operation; prior deterministic validated artifacts retain their original provenance |
| Shared protected configuration | Existing access/policy revision checks conservatively invalidate affected pending operations/approvals; show that impact before signing |
| Toolchain/dependencies/browser/coverage profile | Fresh execution profile/consent and validation evidence where bindings differ; no reuse of stale checks |
| Accepted stack/mapping/layout | Fresh architecture/foundation/affected transformation proposal; no silent overwrite |
| Source/destination/root binding | New setup/rebinding and appropriately scoped artifact/base checks; never redirect an existing approval |

Do not optimize away existing access-digest invalidation merely because a field appears harmless. Any future narrower invalidation must be explicit and tested. A candidate's planned impact list is advisory until the backend rechecks actual current records.

Audit metadata includes request/operation ID, principal, project, old/new digests, affected field names, check references, approver and effective timing. Bounded sanitized diagnostics may be retained. No secret values, complete environment, full provider prompts or private key material enters logs, events, exports or error responses.

## 11. Core/application/API/CLI design

### 11.1 Contracts and dependencies

Proposed typed contracts: field descriptors, project constraints/defaults, local profile, effective configuration with provenance, immutable configuration proposal, check request/result, impact projection and operation receipt. These are design names, not classes created by this planning task.

Use strict, frozen, schema-versioned models with bounded fields/lists and deterministic serialization/digests. Core services orchestrate resolution, authorization, validation and candidate lifecycle through ports. OS paths, Git/governance persistence, filesystem checks, tool/provider probes and framework compatibility live in adapters. No domain import of `Settings`, provider SDK, HTTP, Typer or filesystem implementations.

The registry exposes only fields supported by the selected adapter and policy. Framework-specific version/package mappings stay in framework adapters. Local machine defaults are derived through trusted OS helpers, not reference-project paths or branding.

### 11.2 Proposed Control API

| Endpoint | Purpose and required behavior |
| --- | --- |
| `GET /api/v1/projects/{id}/configuration` | Effective redacted values, origins, current revisions, sections, editability and blockers |
| `GET /api/v1/projects/{id}/configuration/schema` | Versioned supported field descriptors/options and constraints; not arbitrary provider introspection |
| `POST /api/v1/projects/{id}/configuration/proposals` | Save a typed, bounded shared candidate bound to expected revision and request ID; return exact candidate digest/diff |
| `GET /api/v1/projects/{id}/configuration/proposals/{proposal_id}` | Inspect candidate, impact and safe human handoff |
| `POST /api/v1/projects/{id}/configuration/checks` | Check the exact candidate/local profile; explicit flags distinguish offline checks from approved probes; return receipt |
| `POST /api/v1/projects/{id}/configuration/local` | Save only current principal's permitted local/session fields; no protected file/binding mutation |
| `POST /api/v1/projects/{id}/configuration/activate` | Submit an externally obtained signed proof to the existing guarded protected-file activation service; never sign or waive proof |
| `GET /api/v1/projects/{id}/configuration/history` | Bounded/paged authorized revisions and related receipts |

Reuse existing operation status/cancellation/event read contracts for long checks. New-project setup uses a separately scoped local launcher contract, not the bound project's configuration endpoint. Root restarts are returned as typed plans/arguments; the browser does not execute shell strings or auto-restart the server.

All mutations include a request ID and expected active context; candidates/probes additionally identify the exact digest. Enforce bound project identity, session authentication, Origin/Host and CSRF, strict body limits, fresh capabilities and principal-bound idempotency before side effects. Recover lost receipts without reissuing a provider call or signed activation. Return structured errors such as stale base, permission denied, unsupported option, missing prerequisite, unsafe roots, restart required and activation pending, without echoing rejected secret-shaped input.

### 11.3 CLI and MCP parity

Propose a coherent `agent config` command group: `show`, `schema`, `propose`, `check`, `local-set`, `review`, `approve`, `history` and `recover`, with typed JSON output and safe terminal human review. Existing `init`, access/rules approval, execution consent and Foundation Wizard commands remain the authority for their respective lifecycles; aliases can route through the shared service.

Do not force a GUI-only setup. CLI options/environment aliases feed the same resolver and show provenance. MCP may inspect authorized settings and submit bounded candidates/checks under its ceiling; it cannot sign, activate owner changes, grant consent, raise launcher capabilities or supply untrusted raw shell.

## 12. Implementation milestones and dependencies

The original request authorized this plan only. The subsequent user instruction, “ok, proceed for the implementations,” authorized the bounded configuration milestones below. See [implementation report](agent-configuration-management-implementation-report.md) for delivered behavior, verification and retained product boundaries; deferred features remain deferred.

| Milestone | Deliverable | Depends on | Exit criterion |
| --- | --- | --- | --- |
| C0 — Contracts and decisions | Inventory exact setting consumers, decide scope/storage/precedence/permissions, specify destination and wizard remediation prerequisites | Current planning | Reviewed contract and bounded execution scope; no runtime claim |
| C1 — Resolver and read surfaces | Typed contracts/registry, compatibility layer, shared effective resolver, redacted CLI/API read models, explicit capability adoption | C0 | CLI/API/worker values agree; legacy settings are preserved; no authority fallback |
| C2 — Routine local preferences and GUI | Settings routes/overview/models, per-principal permitted saves, provenance/restart UX, offline checks | C1; verified approved profiles for model selection | Eligible users save allowed choices without changing signed project constraints; cached/stale/error cases work. If profile adoption is unavailable until C3, model selection clearly remains blocked |
| C3 — Signed shared settings and safe setup | Immutable proposals/diffs, protected-file activation/recovery, human handoff, directory/setup/restart contracts | C1, verified security/activation decisions | Owner changes are exact and recoverable; viewer/self-elevation/drift tests reject; roots cannot redirect apply |
| C4 — Environment and workflow integration | Environment/browser editors, bounded supervised probes, configuration snapshots in workers, wizard mapping/architecture integration and real readiness | C2–C3, required foundation/destination remediations | Configured environment can progress through production validation; blocked prerequisites remain actionable |
| C5 — End-user acceptance and documentation | Offline full gates, real GUI browser checks, packaging, user/operator guides and upgrade notes | C1–C4 | Verified ordinary-user and owner workflows, with no source modifications and documented residual deployment limits |

Work can be delivered in bounded vertical slices. A read/local-settings release must label unavailable signed activation, target publication or environment features explicitly. Do not advertise full configuration management after only adding forms.

Deferred unless separately authorized: credential vault/OAuth login, arbitrary provider endpoints/plugins, global multi-project daemon, cloud/remote administration, automatic installations, Git membership polling, cross-host trust relocation automation, raw JSON editing, configuration file upload/import/export and automatic server restarts. None is a prerequisite for ordinary project settings inspection.

## 13. Acceptance and quality gates

Focused tests must demonstrate:

1. Configuration precedence is identical in CLI/API/MCP/workers; environment overrides cannot bypass policy or accepted architecture. Effective values include accurate origins.
2. Unknown schema/capability/options, duplicate keys, wildcard grants, secrets and unsafe paths fail closed without input disclosure. Existing unsupported settings are preserved rather than silently rewritten.
3. Viewer, developer, reviewer, operator, owner and custom roles have the documented field/action permissions. New capability grants require signed adoption; users cannot save another principal's local profile or elevate themselves. A configuration-only custom role can enter Settings without plan/run read grants, and unsupported initial profiles do not become implicit provider authorization.
4. Ordinary allowed local model/presentation choices do not trigger owner signatures. Shared protected changes cannot activate through a session token, fake/raw access proof or denied-action fallback.
5. No source file or source manifest changes during inspect/edit/check/save/stage/setup; real source inventories remain identical. Final target publication is unavailable until its destination-aware guard is verified.
6. Provider checks are opt-in, bounded, cancellable, destination-authorized and source-free. Offline use requires no provider key/network; test providers and fixture tools exercise errors/timeouts without external calls.
7. Changed source/governance/access/config/architecture/toolchain/dependency/coverage context invalidates the appropriate candidate, consent or evidence. Model selection cannot redirect a queued operation mid-run.
8. Double submission, lost responses, reload, simultaneous owners and repeated request IDs produce coherent receipts and no duplicate activation/probes. Revoked users cannot replay prior rights.
9. Protected-file/access multi-store interruption recovers from verified intent, rejects oversized/corrupt records and retains anti-rollback floors. Lock ordering avoids access/apply/worker deadlocks.
10. Windows/Linux path, case, junction/link, Unicode, path-budget and LF/CRLF cases are deterministic. Native supervision and consent assertions remain intact; no model-generated shell is accepted.
11. Wizard accepted decisions and actual task/validation evidence determine readiness. ADR count/file presence/fabricated approvals cannot unlock functional migration. Package edit controls round-trip against the same typed domain model.
12. Desktop/mobile, light/dark, keyboard and assistive-technology flows cover navigation, read-only denial reasons, field errors, unsaved edits, restart pending, stale permissions and unknown outcomes. No UI claims an active change before server confirmation.

Before completing an authorized implementation slice, run the repository-required gates:

```text
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run migration-agent doctor
```

For GUI slices also run `npm run test`, lint, format check and production build in `ui/control-center`; perform real desktop/mobile browser acceptance and verify packaged assets match the built source. Use synthetic repositories for mutation/execution regressions and read-only real-source evidence for acceptance. No tests require live credentials or network.

Update user guides, security/architecture decisions, upgrade notes, phase status and an implementation report with actual gate evidence and remaining deployment prerequisites. Doctor success is platform health, not proof of a migrated foundation. No quality-gate suite was run for this document-only planning task.
