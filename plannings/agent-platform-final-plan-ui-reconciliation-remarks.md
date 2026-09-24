# Agent Platform — Final Plan UI & Control-Center Reconciliation Remarks

> **Purpose:** Targeted amendments to the current authoritative master plan.  
> **Status:** Apply these remarks to the final plan; do not redesign or otherwise reopen the frozen architecture.  
> **Source Plan:** `agent-platform-master-plan.md`

---

## 1. Final UI Technology Decision

The Control Center will use:

```text
Angular 21 LTS baseline
        +
Bootstrap 5.3.x utilities only
        +
Mermaid.js
```

Where the plan currently says **Angular 21+ Standalone**, use:

> **Angular 21 LTS baseline, with future upgrades to newer supported Angular majors only after compatibility validation.**

This gives the implementation a stable baseline while preserving a controlled upgrade path.

---

## 2. Bootstrap 5.3.x — Utilities Only

Use **Bootstrap 5.3.x utility classes as the primary and currently only UI styling/layout foundation**.

Use Bootstrap utilities for:

- Layout and responsive structure
- Flexbox/grid
- Spacing
- Typography
- Sizing
- Alignment
- Visibility/display
- Borders/radius
- Color and theme utilities
- Dark-mode presentation

### Required constraint

**Do not use Bootstrap JavaScript plugins as a required application interaction framework.**

Angular owns application behavior and interaction state, including dialogs, navigation, menus, tabs, dropdown behavior, expand/collapse state, approvals, run controls, and WebSocket-driven state.

Bootstrap provides presentation/layout primitives; Angular provides application behavior.

---

## 3. PrimeNG Is Not a Core Dependency

**Do not add PrimeNG to the baseline architecture.**

There must be no mandatory PrimeNG dependency in:

- Core platform distribution
- Control Center baseline
- UI architecture contracts
- Control API contracts
- Domain/application layers
- Platform packaging assumptions

PrimeNG may be evaluated in a future phase only if a concrete UI capability cannot be delivered reasonably with Angular + Bootstrap.

Any future component-library addition must receive a separate review covering:

1. License and redistribution terms
2. Long-term maintenance status
3. Angular-version compatibility
4. Security posture
5. Supply-chain/dependency impact
6. Vendor/framework coupling

The architecture must **not** assume PrimeNG will be adopted later.

The Control Center should depend on platform UI contracts and domain view models, not on a specific third-party component library.

---

## 4. Mermaid Security Requirement

Keep Mermaid.js as the source-driven diagram renderer.

Add:

> **Repository-generated or agent-generated Mermaid content must be rendered using a restrictive Mermaid security configuration. Interactive/clickable behavior and embedded HTML must not be enabled for untrusted diagram sources unless explicitly authorized by policy.**

The GUI must assume that diagrams originating from adopted/untrusted repositories may contain adversarial or unexpected content.

Mermaid remains a rendering mechanism. A future structured canonical architecture model remains the source of truth where one exists.

---

## 5. WebSocket Security Requirement

The Control Center uses HTTP and WebSocket communication with the local Control API.

Add:

> **Every WebSocket connection must authenticate during handshake using the same per-launch session authentication model as the Control API and must pass Origin validation. WebSocket messages remain subject to core authorization and Policy Engine checks; the WebSocket channel must never constitute a policy bypass.**

The security model is:

```text
Browser
  |
  +-- HTTP -----------------------------+
  |                                     |
  +-- WebSocket ------------------------+--> Control API / Core
                                            |
                                            +--> Actor resolution
                                            +--> Session validation
                                            +--> Policy Engine
                                            +--> Authorization
```

A valid session token proves session authenticity only. It does not itself grant privileged capabilities.

---

## 6. Controlled Apply — Attribution Wording

Replace wording equivalent to:

> "Controlled patch application with platform Git attribution."

with:

> **Controlled patch application with explicit actor attribution and configured Git identity.**

Keep the existing distinction between:

- Actor identity
- Git display identity
- ChangeSet approval signing
- Git commit signing
- `committed_by` attribution
- Policy authorization

Git attribution must never be treated as proof of authorization.

---

## 7. Control Center Architecture Boundary

Retain and strengthen the existing boundary:

```text
Angular Control Center
        |
        v
Versioned Control API
        |
        v
Application Services
        |
        v
Domain / Policy
        |
        v
Ports
        |
        v
Infrastructure
```

The Angular GUI must never directly access:

- Git repositories
- Filesystem
- SQLite
- Staging workspaces
- Command runners
- Policy Engine internals
- Model-provider SDKs

All such operations remain behind the Control API and application/domain boundaries.

This preserves the ability to replace the UI technology later without destabilizing the platform core.

---

## 8. Recommended Exact Master-Plan Updates

### Section 3 — UI Technology Stack

Use:

```text
Framework: Angular 21 LTS baseline, Standalone APIs
Reactivity: Angular Signals
Control Flow: Angular modern template syntax
Styling: Bootstrap 5.3.x utilities only
Diagrams: Mermaid.js
Transport: Typed HTTP + authenticated WebSocket via versioned Control API
```

Add:

```text
Bootstrap JavaScript plugins are not a required application interaction
dependency; interactive behavior is implemented by Angular.
No PrimeNG dependency is required or assumed.
```

### ADR-5

Use wording equivalent to:

```text
ADR-5: Decoupled Local Web UI via Versioned Control API

Localhost SPA on loopback (127.0.0.1) built with Angular 21 LTS baseline,
Bootstrap 5.3.x utilities only, and Mermaid.js, with origin checks,
per-launch session authentication, CSRF defenses for state-changing HTTP
operations, authenticated WebSocket handshakes, and zero target-repository
pollution.

The UI contains no direct filesystem, Git, SQLite, staging, or Policy Engine
access. No specific component-library dependency is part of the core
architecture.
```

### Phase 10

Update the GUI implementation focus to:

```text
- Localhost web control center (SPA) served via `agent ui`.
- Angular 21 LTS baseline with Standalone APIs.
- Bootstrap 5.3.x utilities only.
- No mandatory PrimeNG or other third-party component library.
- Loopback-only binding (127.0.0.1).
- Per-launch session token.
- Strict Origin validation.
- CSRF defenses for state-changing HTTP requests.
- Authenticated and Origin-validated WebSocket handshake.
- Backend authorization enforced independently for every privileged operation.
- Visual side-by-side diff review, approval signing, and secure Mermaid rendering.
```

---

## 9. Things NOT to Change

Do not reopen or redesign the following decisions:

- Project-neutral core
- Headless CLI
- Decoupled local GUI
- Loopback-only local Control API
- Git-native identity/authorization model
- Out-of-band trust bootstrap
- Capability-based authorization
- SQLite as authoritative operational run state
- JSONL as audit/export mirror
- SHA-256 raw file hashing
- RFC 8785 canonical metadata hashing
- Base-state binding and drift invalidation
- Controlled staging/apply protocol
- `RecoveryRequired` state
- Policy Engine as the security boundary
- LLM as untrusted proposer
- `AgentRuntimePort` abstraction
- Tiered project knowledge model
- Non-destructive artifact regeneration
- Framework-specific logic remaining in adapters/workflows
- Target project remaining independent of platform runtime code

---

## 10. Final Decision Summary

| Concern | Final Decision |
|---|---|
| SPA framework | **Angular 21 LTS baseline** |
| Component architecture | **Angular Standalone** |
| Reactivity | **Angular Signals** |
| Styling/layout | **Bootstrap 5.3.x utilities only** |
| Bootstrap JS | **Not required for application behavior** |
| Component library | **None required** |
| PrimeNG | **Deferred / optional only after separate review** |
| Architecture diagrams | **Mermaid.js** |
| Local API | **Loopback (`127.0.0.1`)** |
| HTTP security | **Session token + Origin validation + CSRF protections** |
| WebSocket security | **Authenticated handshake + Origin validation + backend authorization** |
| GUI filesystem/Git access | **Prohibited; Control API only** |

### Final architectural position

Use the simplest UI stack that satisfies the Control Center requirements:

> **Angular 21 LTS + Bootstrap 5.3.x utilities + Mermaid.js**

Do not add PrimeNG preemptively.

The platform should keep the UI layer replaceable through the existing Control API boundary rather than embedding assumptions about any specific component library.
