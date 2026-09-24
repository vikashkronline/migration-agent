# Agent Platform — Safe Publication, Distribution & Core IP Protection

## Purpose

This document addresses a future concern:

> **How can the Agent Platform be published and distributed safely to end users while protecting the core implementation and intellectual property, especially when the platform is designed to operate locally without requiring a centralized application server?**

This document is intentionally separate from the current architecture plan.

It should be applied at a suitable later architecture/release-hardening stage, after the core domain, Control API, workflow boundaries, security model, and execution model have stabilized.

**Do not update the main architecture plan yet solely from this document.**

Antigravity/Codex should later review these recommendations and decide how and when they belong in the architecture and delivery roadmap.

---

# 1. The Fundamental Constraint

The most important architectural fact is:

> **If the complete agent implementation runs on an end user's machine, a sufficiently capable end user can inspect, reverse engineer, debug, trace, or modify that implementation.**

This remains true even when the software is:

- compiled,
- packaged as a single executable,
- obfuscated,
- encrypted at rest,
- delivered through an installer,
- protected by licensing,
- signed.

Code signing proves authenticity/integrity of the publisher.

It does not make software that executes locally cryptographically secret from the machine owner.

Likewise:

> **Encryption of the executable does not fundamentally solve local IP protection if the executable must eventually be decrypted and executed on the customer's machine.**

Therefore the architecture must distinguish:

1. **Integrity and authenticity**
2. **Casual source-code protection**
3. **Reverse-engineering resistance**
4. **Protection of secrets**
5. **Protection of proprietary algorithms**
6. **True confidentiality of core implementation**

These are different goals.

---

# 2. Recommended Security Position

For the initial product architecture:

> **Use local distribution with strong integrity/authenticity controls and practical reverse-engineering resistance, but do not claim that locally executed core code is impossible to inspect.**

The architecture should explicitly acknowledge:

```text
Local execution
    ↓
Customer controls machine
    ↓
Customer can theoretically inspect executable
```

The goal should therefore be:

```text
Protect source
+
Protect secrets
+
Protect release integrity
+
Make reverse engineering materially harder
+
Keep proprietary interfaces narrow
+
Move true crown-jewel secrets/logic off the client only when required
```

---

# 3. Separate Open Project Artifacts From Proprietary Platform Implementation

The platform should maintain a deliberate separation between:

## Target project / user-owned artifacts

These are expected to be visible and version-controlled:

- application source code,
- project configuration,
- project `.agent/` metadata,
- architecture documentation,
- project decisions,
- project learnings,
- project-specific workflow configuration.

## Platform-owned implementation

Potentially proprietary:

- core orchestration implementation,
- internal policy algorithms,
- proprietary workflow implementations,
- internal prompt construction logic,
- internal model-routing logic,
- proprietary optimization algorithms,
- internal telemetry/diagnostic logic,
- proprietary agent techniques.

The user should interact through stable contracts rather than needing access to the core source code.

This follows the existing architectural direction in which the target project remains independently usable and the local GUI communicates with the headless engine through the Control API.

---

# 4. Recommended Distribution Architecture

The preferred end-user distribution should look conceptually like:

```text
                   Official Release Pipeline
                           │
                           ▼
                  Source Build Environment
                           │
            ┌──────────────┼───────────────┐
            │              │               │
            ▼              ▼               ▼
        Core Binary   GUI Assets       Workflow Bundles
            │              │               │
            └──────────────┼───────────────┘
                           ▼
                    Release Artifact
                           │
                    Code Signature
                           │
                    Release Manifest
                           │
              Checksum / Integrity Metadata
                           │
                           ▼
                  User Installation
                           │
                           ▼
                  Local Agent Platform
```

The user's machine receives a product artifact rather than the development repository.

---

# 5. Recommended Distribution Forms

Different audiences can receive different packaging levels.

## A. Development distribution

For internal development or trusted contributors:

- source repository,
- editable Python/package environment,
- full test suite,
- development GUI,
- debug tools.

This is the easiest form and should remain available internally.

## B. Standard end-user distribution

For normal users:

- native executable or packaged application,
- production GUI assets,
- only required runtime components,
- no development source tree,
- no test/debug infrastructure,
- no source maps for proprietary frontend code,
- no internal development credentials.

Examples of conceptual packaging:

```text
agent-platform
agent-ui assets
runtime dependencies
workflow bundles
license metadata
release manifest
```

## C. Restricted/proprietary enterprise distribution

For higher-value proprietary components:

- signed binaries,
- selectively packaged proprietary workflows,
- externally supplied configuration,
- optional feature/license manifests,
- stronger runtime hardening.

This is still client-side and therefore not absolute secrecy.

---

# 6. Do Not Ship Secrets With the Agent

This should be a non-negotiable invariant.

Never embed:

- private signing keys,
- platform master keys,
- customer API secrets,
- database passwords,
- cloud credentials,
- unrestricted access tokens,
- private repository credentials,
- universal encryption/decryption keys.

Do not assume that:

```text
"obfuscated secret inside the binary"
```

is a secret.

If a key is available to the running application, a determined customer may be able to extract it.

Secrets should instead come from:

- user's own credential store,
- OS secret manager,
- environment configuration,
- user-provided credentials,
- explicitly configured provider integrations.

---

# 7. Code Signing Should Be Mandatory for Published Releases

Every published executable/installer/package should be signed by the publisher's release identity.

Conceptually:

```text
Build
  ↓
Artifact
  ↓
Digest
  ↓
Publisher Signature
  ↓
Release Manifest
```

The user installation/update process should verify:

```text
Signature
+
Publisher identity
+
Expected artifact digest
+
Compatibility metadata
```

This protects against:

- tampered downloads,
- malicious package substitution,
- accidental distribution of modified builds,
- compromised mirrors,
- partial/corrupt downloads.

Code signing solves **authenticity and integrity**, not source secrecy.

---

# 8. Use a Signed Release Manifest

Every release should have a machine-readable manifest.

Conceptually:

```yaml
release:
  product: agent-platform
  version: 1.4.0
  platform: windows-x64

artifacts:
  - name: agent-platform.exe
    sha256: ...
    signature: ...

components:
  core: 1.4.0
  control_api: 1.3
  gui: 1.4.0
  workflow_schema: 2

compatibility:
  project_manifest_min: 1
  project_manifest_max: 3

security:
  minimum_supported_version: 1.3.0
```

This provides:

- deterministic release identification,
- component compatibility,
- rollback support,
- update safety,
- installation validation.

---

# 9. Prefer an Immutable Release Artifact

A published version should be immutable.

For example:

```text
agent-platform-1.4.0-windows-x64.exe
```

Once published:

```text
1.4.0
```

must never silently change its content.

If a build changes:

```text
new artifact
new digest
new release version
```

This is particularly important because the architecture uses content digests for ChangeSets and approvals.

---

# 10. Reproducible or Verifiable Builds

As the product becomes commercially or operationally important, the release pipeline should strive toward reproducible or independently verifiable builds where practical.

The goal is:

```text
Source revision
      ↓
Build
      ↓
Artifact
      ↓
Known digest
```

with a verifiable relationship between them.

At minimum, record:

- source revision,
- build environment/version,
- dependency lock information,
- build timestamp metadata where appropriate,
- artifact digest,
- signing identity.

This is a supply-chain integrity concern, not merely an IP-protection feature.

---

# 11. Protect the Frontend as Well as the Core

If the GUI is distributed as a local SPA:

```text
HTML
JS
CSS
source maps
```

then users can inspect the JavaScript.

Therefore for proprietary production releases:

- do not ship development source maps,
- minify/bundle production assets,
- remove debug-only endpoints,
- remove development diagnostics,
- avoid embedding internal design notes,
- avoid exposing hidden feature flags that reveal unreleased architecture,
- keep authoritative policy checks in the core rather than relying on frontend concealment.

The GUI must never contain the actual security enforcement logic.

---

# 12. Never Put Security-Critical Logic Only in the GUI

The GUI is a presentation client.

Therefore:

```text
GUI says:
"Approve ChangeSet"
        ↓
Core re-validates:
- actor
- capability
- policy
- ChangeSet digest
- base revision
- approval requirements
```

Never rely on:

```text
disabled button
hidden menu
frontend role check
```

for security.

A user can alter browser code.

The current architecture already establishes the GUI as an untrusted client of the Control API; publication should preserve this boundary.

---

# 13. Protect Proprietary Prompt/Agent Logic Realistically

If proprietary system prompts, reasoning templates, agent instructions, or routing logic are shipped locally:

> they should be considered recoverable by a determined user.

Practical measures can still reduce casual exposure:

- compile/pack prompts into application resources,
- remove plaintext development prompt files,
- minimize detailed internal comments from production resources,
- separate public configuration from internal instructions,
- avoid exposing raw internal prompts through API responses,
- avoid returning hidden chain-of-thought-like internal data,
- log summaries and structured decisions rather than private internal reasoning.

However:

> **Do not treat locally packaged prompts as secrets.**

If absolute confidentiality of proprietary logic becomes a business requirement, the corresponding logic must run in a trusted environment outside the end-user-controlled machine.

---

# 14. The True Crown-Jewel Decision

At some point the product may identify logic that must not be distributed to customers.

For example:

```text
Proprietary optimization engine
Proprietary model-routing algorithm
Highly sensitive intellectual property
Commercial licensing enforcement logic
```

There are only a few reliable architectural options.

## Option A — Local distribution

```text
User machine
    ↓
Core executes locally
```

Advantages:

- offline,
- local-first,
- no central service dependency.

Limitation:

- determined user can reverse engineer it.

## Option B — Remote protected service

```text
Local agent
    ↓
Authenticated API
    ↓
Protected proprietary service
```

Advantages:

- actual implementation remains outside customer machine.

Limitations:

- requires network infrastructure,
- service availability dependency,
- higher operational complexity,
- conflicts with a strictly offline/local-only deployment.

## Option C — Trusted execution environment

A specialized trusted hardware/isolated-execution architecture can protect certain workloads.

This is technically possible but materially more complex and should not be part of the initial platform.

---

# 15. Recommended Product Strategy

Do not force the entire platform to become server-based merely to protect ordinary implementation details.

Instead split the product into:

```text
Local Core
    ↓
Safe to distribute as hardened executable

Optional Protected Service
    ↓
Only for true crown-jewel logic when required
```

This preserves the original local-first architecture while leaving a future option open.

---

# 16. Workflow Distribution

The architecture uses workflow modules.

That creates a useful distribution mechanism.

A workflow package can contain:

```text
Workflow
├── manifest
├── compatible core version
├── workflow implementation
├── capabilities required
├── policy requirements
├── UI metadata
└── integrity/signature metadata
```

Before loading a workflow:

```text
Verify signature
      ↓
Verify publisher
      ↓
Verify compatibility
      ↓
Verify requested capabilities
      ↓
Policy evaluation
      ↓
Load workflow
```

Untrusted workflow packages should never gain unrestricted capabilities merely because they are installed.

---

# 17. Workflow Capability Declarations

Each distributed workflow should declare the capabilities it needs.

For example:

```yaml
workflow:
  id: architecture-discovery
  version: 1.2

requires:
  capabilities:
    - project.read
    - filesystem.inspect
    - analysis.execute
```

A migration workflow might require:

```yaml
requires:
  capabilities:
    - project.read
    - changeset.stage
    - validation.execute
```

A workflow requesting:

```text
policy.write
```

or:

```text
changeset.apply
```

should trigger much stronger policy/approval requirements.

This prevents a proprietary or third-party workflow from quietly obtaining all platform capabilities.

---

# 18. Component Trust Levels

Consider defining distribution trust levels.

```text
CORE TRUSTED
    Officially signed platform core.

OFFICIAL WORKFLOW
    Signed by platform publisher.

PROJECT WORKFLOW
    Signed or explicitly trusted by project owner.

THIRD-PARTY WORKFLOW
    Explicitly enabled by user/project policy.

UNTRUSTED
    Cannot execute privileged capabilities.
```

This works naturally with the existing Policy Engine.

---

# 19. License/Feature Control Without Mandatory Server Infrastructure

If commercial licensing eventually becomes necessary, a signed license artifact can work for a local-first product.

Conceptually:

```text
License File
├── customer/project
├── product tier
├── enabled capabilities
├── expiration (optional)
├── issue timestamp
└── publisher signature
```

The client verifies the publisher signature using an embedded public key.

This avoids a mandatory license server.

However:

> Local license enforcement is not cryptographically unbreakable because the customer controls the executable.

Therefore signed licenses should be viewed as:

- legitimate entitlement enforcement,
- auditability,
- operational control,

not as perfect anti-tampering protection.

---

# 20. Public Key vs Private Key in the Product

A useful rule:

```text
Public verification key
    → may be embedded in the application

Private signing key
    → NEVER shipped
```

The build/release infrastructure holds private signing keys.

Users receive artifacts containing only the information required for verification.

This applies to:

- release signatures,
- workflow package signatures,
- policy-authority verification,
- license verification.

---

# 21. Release Pipeline Security

The publishing pipeline itself becomes part of the security architecture.

Recommended conceptual pipeline:

```text
Developer commit
      ↓
Protected source branch
      ↓
Automated tests
      ↓
Security checks
      ↓
Build
      ↓
Artifact scan
      ↓
Artifact digest
      ↓
Signing
      ↓
Release manifest
      ↓
Publish
```

The signing key should be protected separately from normal developer credentials.

Do not allow ordinary source changes to automatically gain unlimited release-signing authority.

---

# 22. Update Mechanism

A future updater should verify the new release before replacing the current binary.

Conceptually:

```text
Check available version
      ↓
Download artifact
      ↓
Verify manifest signature
      ↓
Verify artifact digest
      ↓
Verify publisher identity
      ↓
Verify compatibility
      ↓
Install side-by-side / transactionally
      ↓
Health check
      ↓
Activate
```

If activation fails:

```text
Rollback
```

A local/offline installation should still support updates from a manually supplied signed artifact.

---

# 23. Release Revocation

The platform should have a way to reject known-compromised releases.

Possible local model:

```text
minimum_supported_version
revoked_release_ids
revoked_signing_keys
```

These can be delivered through:

- signed update metadata,
- official release bundles,
- later optional online metadata.

For fully offline users, a newly distributed signed policy/configuration package can carry revocation information.

---

# 24. Do Not Expose Internal Architecture Through Diagnostic APIs

Production builds should avoid unrestricted endpoints such as:

```text
/debug
/internal/state
/dump-config
/raw-prompt
/full-agent-context
/raw-policy-engine
```

unless explicitly authenticated and authorized for development builds.

The Control API should expose domain information required by the GUI, not internal implementation details.

For example:

Preferred:

```text
GetRun()
GetRunEvents()
GetChangeSet()
GetAuthorizationDecision()
GetArtifact()
```

Avoid:

```text
GetInternalAgentMemoryGraph()
DumpAllInternalState()
GetPromptConstructionGraph()
```

unless these are explicitly designed public APIs.

---

# 25. Logging and IP Leakage

Logs can unintentionally leak more IP than the executable itself.

Production logs should avoid:

- full internal prompts,
- proprietary reasoning traces,
- hidden tool instructions,
- proprietary algorithm parameters,
- embedded source code,
- customer secrets,
- private environment values,
- internal development paths.

Prefer structured records such as:

```text
Run ID
Workflow ID
Action
Policy decision
ChangeSet digest
Validation result
Error category
Artifact references
```

This aligns with the platform's existing audit/run model.

---

# 26. Error Messages Need Two Levels

Production errors should distinguish:

```text
User-facing diagnostic
```

from:

```text
Developer diagnostic
```

Example:

User-facing:

```text
Validation failed.
See Run #1842 for details.
```

Internal diagnostic:

```text
exact stack trace
internal adapter path
implementation details
```

The internal diagnostic should only be available under controlled diagnostic permissions or development builds.

---

# 27. Protect the Agent's Own Update and Workflow Mechanisms

The agent should not be able to:

```text
download arbitrary executable
replace core binary
replace signing keys
change update source
disable signature validation
modify trust roots
disable Policy Engine
```

through ordinary project workflows.

These are **platform self-management operations** and should be outside normal agent capabilities.

A platform update should be a distinct trusted operation.

---

# 28. Platform Self-Update vs Project Modification

Keep these as separate domains:

```text
Project Change
    ↓
ChangeSet → Approval → Apply

Platform Update
    ↓
Signed Release Artifact → Verification → Installation
```

The ordinary agent should not be able to turn a project ChangeSet workflow into a mechanism for replacing the platform itself.

---

# 29. Protect the Project From Malicious Workflow Packages

Because workflows may execute commands or modify project files, package integrity matters.

Before installing a workflow:

```text
Package signature valid?
Publisher trusted?
Version compatible?
Requested capabilities acceptable?
Policy allows installation?
```

Then record:

```text
Installed Workflow
├── version
├── publisher
├── signature
├── capabilities
└── installation time
```

This should be auditable.

---

# 30. Distribution Does Not Mean the End User Must See the Full Architecture

The product can intentionally expose only the conceptual information required by the user.

For example, users may see:

```text
Workflow: Architecture Discovery
Status: Running
Progress: 68%
Current operation: Dependency analysis
Result: 14 components discovered
```

They do not necessarily need to see:

```text
internal Python module structure
agent prompt templates
private routing heuristics
internal adapter implementation
source build metadata
internal testing utilities
```

This is a product/interface concern rather than cryptographic secrecy.

---

# 31. What Can Be Safely Exposed

The user should still see the information necessary to preserve transparency and trust.

The product should expose:

- actions being performed,
- current status,
- approvals required,
- ChangeSet summary,
- affected files,
- validation results,
- policy decisions relevant to the operation,
- user-facing errors,
- artifacts,
- documentation,
- decisions,
- provenance.

The product should not need to expose its private implementation.

This preserves the platform's human-governed model without revealing all internal mechanisms.

---

# 32. Threat Model to Add Later

When this topic is incorporated into the main architecture, explicitly distinguish threats.

## Threat A — Malicious package/release

Mitigations:

- signed artifacts,
- signed manifests,
- checksum verification,
- protected release keys,
- trusted update channel.

## Threat B — Accidental tampering

Mitigations:

- signatures,
- immutable releases,
- installation validation,
- health checks.

## Threat C — Casual source inspection

Mitigations:

- compiled binaries,
- production bundling,
- symbol stripping,
- minification,
- source-map removal.

## Threat D — Serious reverse engineering

Mitigations:

- native compilation,
- obfuscation where justified,
- minimized exposed logic,
- selective remote execution for crown-jewel components.

No client-only technique makes this threat disappear.

## Threat E — Secret extraction

Mitigation:

> Never ship secrets.

Do not attempt to solve secret protection through obfuscation.

---

# 33. Recommended Future Architecture

A mature version could support:

```text
                 Product Distribution
                         │
             ┌───────────┴───────────┐
             │                       │
        Local Platform          Optional Services
             │                       │
       Signed Binary           Protected API
       Signed Workflows        Cloud/Enterprise
       Local Policy            Proprietary Logic
       Local Git               Optional Shared State
             │                       │
             └───────────┬───────────┘
                         │
                    Control Model
```

The optional service should never become a hidden prerequisite for the local core.

---

# 34. Recommended Stage for the Main Plan

Do not add this as an immediate Phase 1 architectural requirement.

A suitable point is:

> **After the core architecture, Control API, workflow contracts, Policy Engine, and local GUI have stabilized, and before external/customer distribution.**

Practically, this can be a later:

```text
Distribution & Release Hardening
```

stage within or after the future **Extensibility & Ecosystem** phase.

A sensible dependency chain is:

```text
Core contracts stabilized
        ↓
Workflow packaging stabilized
        ↓
Control API stabilized
        ↓
GUI production build stabilized
        ↓
Security model stabilized
        ↓
Distribution / Signing / Update architecture
        ↓
External distribution
```

The distribution design should not prematurely constrain the core architecture.

---

# 35. Recommended Future ADR Set

When this topic is incorporated into the main plan, consider separate ADRs rather than one large security ADR:

### ADR — Production Packaging & Distribution

Defines:

- executable/package formats,
- separation of development and production builds,
- artifact composition.

### ADR — Release Signing & Integrity

Defines:

- signing,
- manifests,
- digests,
- trust roots,
- release verification.

### ADR — Workflow Package Trust

Defines:

- signed workflows,
- publishers,
- capability declarations,
- installation policy.

### ADR — Secure Update & Rollback

Defines:

- signed update manifests,
- update verification,
- rollback,
- revocation.

### ADR — Proprietary Core IP Protection

Defines:

- what is protected,
- what is intentionally exposed,
- realistic reverse-engineering expectations,
- optional future protected services.

Do not create all of these now unless the product actually reaches the corresponding maturity.

---

# 36. Architectural Invariants to Add at the Appropriate Stage

Future distribution architecture should eventually include invariants such as:

1. Production releases are cryptographically signed.
2. Published artifacts are immutable by version.
3. Private release/signing keys never ship with the product.
4. Secrets never ship inside binaries or packages.
5. GUI code is not a security boundary.
6. Core authorization is enforced outside the frontend.
7. Workflow packages declare required capabilities.
8. Untrusted workflows cannot automatically obtain privileged capabilities.
9. Platform update mechanisms are separate from project mutation workflows.
10. Release verification occurs before installation or update.
11. Local execution is not represented as impossible to reverse engineer.
12. Proprietary logic requiring absolute confidentiality must not rely solely on client-side secrecy.
13. User-facing diagnostics must not expose unnecessary implementation/IP details.
14. Production builds must not expose development-only diagnostics.
15. The local-first core must remain usable without a proprietary remote service unless the specific feature explicitly requires one.

---

# 37. Practical Recommendation for This Platform

For the current product direction, the most balanced strategy is:

```text
Core Platform
    ↓
Compiled/packaged local executable
    +
Signed release
    +
Signed workflow packages
    +
Git-native project state
    +
Local Policy Engine
    +
Local GUI
```

Protect source/IP through:

```text
production packaging
+
native compilation where useful
+
symbol/debug stripping
+
frontend bundling/minification
+
removal of development artifacts
+
limited internal API exposure
```

Protect actual secrets through:

```text
never shipping secrets
+
OS credential stores
+
user-provided credentials
```

Protect release integrity through:

```text
publisher signatures
+
signed release manifests
+
artifact digests
+
validated updates
```

Protect crown-jewel implementation through:

```text
optional future remote/protected execution
```

only where the business requirement justifies the operational trade-off.

---

# 38. Final Decision Principle

The architecture should **not promise "the end user cannot see the core."**

It should promise something more accurate:

> **The production distribution does not expose the development source tree or internal implementation artifacts, release artifacts are cryptographically authenticated, secrets are not embedded, privileged operations remain policy-controlled, and proprietary components that require stronger confidentiality can be isolated behind an optional protected execution boundary.**

This is a technically defensible product promise.

---

# 39. Instructions to Antigravity / Codex for the Future

When this document is eventually applied:

1. Review it against the final architecture.
2. Determine which distribution requirements are actually needed for the intended release model.
3. Do not assume that source-code concealment equals cryptographic secrecy.
4. Preserve the local-first architecture.
5. Do not introduce a mandatory application server solely for IP protection.
6. Introduce a remote protected service only for logic that truly requires confidentiality beyond client-side protection.
7. Add production packaging, signing, release manifests, and update verification only after the core contracts have stabilized.
8. Treat workflow packages as potentially executable extensions and therefore subject them to trust/capability policies.
9. Ensure the GUI cannot become a security bypass.
10. Ensure platform self-update is separate from normal project modification.
11. Explicitly document the remaining limitations of local security.
12. Keep distribution concerns out of the core domain unless they affect a core contract.

---

# 40. Final Recommendation

The current local-first architecture remains viable.

The recommended approach is:

> **Distribute the platform as a signed production application rather than source code, protect release integrity with cryptographic signing and manifests, keep secrets out of the distribution entirely, limit exposed internal implementation details, treat workflows as signed/capability-declared extensions, and accept that code executing on a customer's machine can ultimately be reverse engineered.**

Only introduce server-side protected execution when there is a concrete requirement for **true confidentiality of a particular proprietary component**.

This allows the platform to retain its most important architectural property:

> **The Agent Platform remains usable locally and offline without forcing every user or project into a centralized server-based architecture.**
