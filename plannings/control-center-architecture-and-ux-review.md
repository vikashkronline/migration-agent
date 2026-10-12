# Architectural & UX Review: Generic Control Center Tree Plan vs. Master Architecture Plan

> **Date:** 2026-10-07  
> **Target Plans Reviewed:**  
> 1. `plannings/final/agent-platform-master-plan.md` (Authoritative Platform Master Architecture)  
> 2. `plannings/control-center-tree-ux-wireframe-plan.md` (Generic Control Center — Hierarchical UX & Wireframe Baseline)  
> **Companion References:**  
> - `plannings/control-center-wireframes.html` (Interactive Prototype)  
> - `plannings/control-center-generic-ux-wireframe-plan.md` (Preceding Flat UX Specification)  
> - `docs/phase-status.md` (Current Phase 16 Completed Baseline)  
> **Status:** Review Findings & Risk Assessment for Approval  

---

## 1. Executive Summary & Alignment Verdict

### Overall Assessment: Strongly Aligned (Feasible with 6 Concrete Mitigations)

The proposed **Hierarchical Workstream & Architecture Tree** plan (`control-center-tree-ux-wireframe-plan.md`) represents a major conceptual and architectural advancement over earlier flat navigation prototypes. It directly realizes the master platform vision outlined in **Section 3 (UI / Project Control Center)** and **Section 13 (Phase 10)** of `plannings/final/agent-platform-master-plan.md`.

By organizing the Control Center as a **dependency-driven workstream tree**, the plan correctly:
1. Elevates **Core Platform & Foundation Readiness** to a mandatory prerequisite gate rather than an obscure configuration tab.
2. Models the migration as an engineering workstream DAG: **Foundation & NFRs → Global ADRs & Standards → Functional Modules → Feature Components → Ordered Migration Steps**.
3. Replaces flat, disconnected utility tabs (raw diffs, raw logs, raw viewports) with **context-aware surgical views** that adapt dynamically to the level of the selected node.
4. Preserves **project neutrality**: the common platform core remains generic, while migration-specific workflows (Ember Classic to Angular Standalone) are pluggable extension payloads.

However, moving from a static wireframe prototype to an enterprise-grade Angular 21 LTS implementation introduces **6 architectural gaps and operational risks** across the Control API, real-time event synchronization, large-tree scalability, and approval channels. These must be addressed in the implementation phase.

---

## 2. Feature & Invariant Alignment Analysis

| Master Plan Requirement / Invariant | How Tree Plan (`control-center-tree-ux-wireframe-plan.md`) Aligns | Alignment Status |
|---|---|---|
| **Invariant 1: LLM as Untrusted Proposer** | Model statements are explicitly labeled as proposals with sources; verified results come from durable SQLite checkpoints and signed ChangeSets. | **Full Alignment** |
| **Invariant 5 & 6: Explicit Human Approval & Exact Binding** | Step 5 displays canonical RFC 8785 Plan digest, ChangeSet digest, and active policy digest; approval is single-use and cannot be minted by model tools. | **Full Alignment** |
| **Invariant 8: 4-Step Controlled Apply Protocol** | Apply requires preflight dry-run, backup snapshots in `state_dir`, postconditions, and clean rollback transitioning to `RecoveryRequired` on double-fault. | **Full Alignment** |
| **Invariant 10: Control API Decoupling & Security** | SPA is strictly decoupled on loopback (`127.0.0.1`), authenticated via per-launch session tokens, CSRF tokens on mutating requests, and Origin validation. Zero direct filesystem/SQLite access. | **Full Alignment** |
| **Invariant 16: Bounded Self-Improvement** | Curated learnings and challenge solutions are human-curated and promoted only from passing runs committed to Git (`.agent/learnings/`). | **Full Alignment** |
| **Invariant 19: Staging Confinement & Distinct Roots** | Workspace views strictly distinguish target repository root, isolated staging root, and user-data state directory. | **Full Alignment** |
| **Invariant 34: Native Execution Supervision** | Surfaces active Windows Job Object process confinement, installed Node toolchain, and separate Linux guardian status in Foundation views. | **Full Alignment** |
| **Phase 16 Amendment: Browser UI/UX Validation** | Integrates multi-viewport responsive captures (360x800, 768x1024, 1440x900), DOM/ARIA tree inspection, and visual rule compliance matrix. | **Full Alignment** |

---

## 3. Key Strengths of the Proposed UX Architecture

1. **Dependency Gating (Foundation as a Prerequisite)**:
   - In traditional tools, environment misconfigurations (e.g. missing Node binary, corrupt staging roots, unverified execution guardians) fail cryptically during runtime.
   - The tree plan surfaces **Foundation Readiness** (App Setup, Angular Shell, NFRs & Sandboxing, Shared Services) as the first major root step. If prerequisites are not satisfied, dependent feature applies are visibly blocked with clear remediation links.

2. **Nuanced Readiness Rules (Avoiding False Blockers)**:
   - Crucially, the plan specifies: *"Do not require universal 100% foundation completion for all work."*
   - Planning and inspection remain accessible even if execution sandboxing is unconfigured. A developer can inspect diffs and plan steps without being artificially locked out by an unrun optional check (e.g. optional observability or optional E2E).

3. **Truthful Aggregations & Denominators**:
   - Rejects deceptive vanity metrics (e.g. "95% complete" based merely on generated lines of code or elapsed time).
   - At every level, status labels reflect verified durable postconditions, clearly distinguishing between *Backlog*, *Staged*, *Validated*, *Approved*, and *Applied*.

4. **Dynamic Context-Aware Viewport**:
   - Selecting a **Module** renders an Executive Rollup Dashboard.
   - Selecting a **Feature** renders the Component Architecture & Dependency Card.
   - Selecting a **Step** renders the exact surgical tool needed (Step 2: Staged Diff; Step 4: Browser UI/UX Review; Step 5: Approval Signing Card; Step 6: Apply Status & Backups).

---

## 4. Identified Gaps, Technical Risks & Concrete Mitigations

### ⚠️ Gap 1: Control API Lacks a Hierarchical Tree Projection Endpoint (Priority: High)
- **Finding:**
  The current Python backend (`ControlApiService` in `src/migration_agent/application/control_service.py` and `_ControlApiRequestHandler` in `src/migration_agent/adapters/control_api/server.py`) exposes flat, entity-based endpoints:
  - `GET /api/v1/runs`
  - `GET /api/v1/plans/{id}`
  - `GET /api/v1/graph`
  - `GET /api/v1/learnings`
  It has **no endpoint** returning the unified, hierarchical workstream tree structure specified by the UX plan.
- **Risk:**
  If the frontend Angular application is forced to fetch separate runs, plans, policies, and health checks and stitch them into a tree client-side, **domain and workflow aggregation logic will leak into the presentation layer**, violating Invariant 10 and hexagonal architecture boundaries.
- **Mitigation:**
  Define a typed `WorkstreamTreeProjection` in the application layer and expose a dedicated read-only endpoint:
  ```text
  GET /api/v1/workstreams/tree
  ```
  The backend application service will assemble the project tree from the canonical `checkpoint_port`, `governance_port`, and active `policy`, returning a typed node hierarchy with stable node IDs, status badges, dependencies, and route targets.

---

### ⚠️ Gap 2: Real-Time Tree State Reconciliation & WebSocket Granularity (Priority: High)
- **Finding:**
  The current WebSocket broadcaster (`broadcaster.py` / `_event_sequence`) broadcasts coarse pipeline events (`RUN_STARTED`, `CHECKPOINT_SAVED`, `PLAN_APPROVED`, `RUN_APPLIED`).
  When a multi-stage migration runs (e.g. Stage → Validate → Browser Capture → Repair), multiple nodes in the tree change state sequentially.
- **Risk:**
  Without fine-grained event models, the UI may either:
  1. Fall back to aggressively re-fetching the entire tree on every WebSocket ping (causing UI flickering and scroll jumps).
  2. Experience state drift where a child step shows `VALIDATION_PASSED` but the parent Module badge remains stuck in `STAGED`.
- **Mitigation:**
  Extend the WebSocket event payload with node-specific updates:
  ```json
  {
    "event_type": "NODE_STATE_CHANGED",
    "sequence_id": 42,
    "payload": {
      "node_id": "step-usercard-val",
      "ancestor_ids": ["mod-user", "feat-usercard"],
      "new_state": "VALIDATION_PASSED",
      "readiness_delta": { "passed_gates": 4, "total_gates": 4 }
    }
  }
  ```
  Angular Signals will update only the targeted node and its ancestors reactively without refreshing the entire tree.

---

### ⚠️ Gap 3: Scalability for Repositories with Large Component Inventories (Priority: Medium)
- **Finding:**
  The wireframe prototype illustrates a mini fixture with 1–2 modules and 2 features. In a production enterprise migration (e.g. 50–200 components across 15 modules), expanding all branches would create hundreds of DOM nodes.
- **Risk:**
  Large DOM sizes cause UI lag, while fetching complete diffs, validation digests, and screenshot manifests for every component upfront causes heavy memory consumption and slow initial load times.
- **Mitigation:**
  Implement a **two-tier loading strategy**:
  1. **Tree Skeleton**: The initial tree payload contains only Root, Foundation, Module, and Feature headers with precomputed summary counters.
  2. **Lazy-Loaded Step Details**: When a user expands a Feature component or selects a Step, the detailed step payload (staged diff lines, screenshot binary streams, ARIA accessibility tree dumps) is fetched on demand via `GET /api/v1/workstreams/nodes/{node_id}/detail`.

---

### ⚠️ Gap 4: Human Approval Channel Ambiguity (Mode B vs. Mode A) (Priority: Medium)
- **Finding:**
  Line 95 of `control-center-tree-ux-wireframe-plan.md` states:
  > *"Until a GUI human-only channel is independently accepted, the design uses the existing trusted-terminal handoff; required Mode A authority cannot be replaced by Mode B."*
  However, in Phase 11 and Phase 16, Mode B assurance (trusted local developer session) was formally defined and implemented, anchoring authority to the active operating system user (`getpass.getuser()`) bound to the loopback session token.
- **Risk:**
  If the GUI completely disables in-browser approval and forces the user to switch to a terminal for every single step, the primary UX benefit of the Control Center (interactive review and sign-off) is diminished.
- **Mitigation:**
  Clearly partition approval handling by **Assurance Level**:
  - **Mode B (Local Trusted Session)**: The Control Center provides a direct, one-click interactive approval card with the user's OS identity and CSRF validation, satisfying local developer workflows.
  - **Mode A (Cryptographic Production Sign-off)**: When policy strictly demands Mode A (Ed25519 external signature), the GUI displays the canonical payload to sign with an interactive "Signature Paste" box or terminal-assisted command prompt (`agent approve --mode-a`).

---

### ⚠️ Gap 5: Deep-Linking & History Navigation Contract (Priority: Low)
- **Finding:**
  The tree wireframe is currently interactive within an in-memory session. The plan states that stable URLs and browser back/forward navigation are future implementation requirements.
- **Risk:**
  If a developer bookmarks a specific step diff or refreshes the page while inspecting Step 4 (Browser UI/UX Review), an unhandled deep-link could reset the UI to the root overview, causing significant user frustration.
- **Mitigation:**
  Implement standard Angular route hierarchy with route resolvers:
  ```text
  /workstreams
  /workstreams/foundation/:sectionId
  /workstreams/decisions/:decisionId
  /workstreams/modules/:moduleId
  /workstreams/modules/:moduleId/features/:featureId
  /workstreams/modules/:moduleId/features/:featureId/steps/:stepId
  ```
  Every route resolver must verify that if the in-memory tree is unpopulated (e.g. direct URL entry), it fetches the state dynamically from the backend before rendering.

---

### ⚠️ Gap 6: Frontend Engineering & Design Standard Enforcement (Priority: Strict)
- **Finding:**
  `control-center-tree-ux-wireframe-plan.md` is written as a portable interaction specification. When implemented in `ui/control-center/`, it must adhere strictly to the project's non-negotiable frontend rules.
- **Enforcement Checklist for Implementation**:
  - [x] **Angular 21 LTS Standalone Only**: Every component must have `standalone: true` and `changeDetection: ChangeDetectionStrategy.OnPush`.
  - [x] **Modern Control Flow**: Strictly `@if`, `@else`, `@for (...; track ...)`, `@switch`. Zero legacy `*ngIf` or `*ngFor`.
  - [x] **Reactivity**: Angular Signals (`signal()`, `computed()`) for state; `inject()` for dependency injection.
  - [x] **Styling**: Bootstrap 5.3.x utility classes only (`ms-*`/`me-*`, `d-flex gap-*`); native dark mode support (`data-bs-theme="dark"`).
  - [x] **Zero Third-Party Component Libraries**: No PrimeNG or external widget libraries.
  - [x] **No Bootstrap JS Plugins**: Angular controls all modals, collapses, and dropdowns.
  - [x] **Mermaid Isolation**: Render diagrams strictly via `mermaid.js` with `securityLevel: 'strict'`.

---

## 5. Actionable Roadmap for Implementation

To proceed safely from the approved plan to working code, follow this phased execution sequence:

```text
Step 1: Backend Tree Projection API
        ├── Implement WorkstreamTreeService in Python application layer
        └── Add GET /api/v1/workstreams/tree and node detail endpoints

Step 2: Angular Workspace & Scaffolding
        ├── Configure Angular 21 LTS AOT build (angular.json, tsconfig.json)
        └── Setup root shell with Bootstrap 5.3 utilities and theme service

Step 3: Workstream Tree Navigation Component
        ├── Implement collapsible tree with status badges (Ready, Blocker, Pass)
        └── Implement deep-linked routing with parameter resolvers

Step 4: Viewport & Surgical Tool Components
        ├── Module Rollup Dashboard
        ├── Staged Side-by-Side Diff Viewer
        ├── Phase 16 Browser UI/UX Responsive Carousel & ARIA Tree
        └── Human Approval Card (Mode B signing & Mode A terminal handoff)

Step 5: Production Compilation & Offline Bundling
        ├── Compile production bundle into src/migration_agent/ui/static/
        └── Enforce strict CSP headers without 'unsafe-eval' in server.py

Step 6: Quality Gates & Browser Smoke Verification
        └── Run all 6 platform quality gates and verify agent ui launch
```

---

## 6. Conclusion

The **Hierarchical Workstream & Architecture Tree** plan (`control-center-tree-ux-wireframe-plan.md`) is **architecturally sound, highly aligned with the Master Plan, and ready for implementation** once the 6 technical mitigations above are incorporated.

It elevates the platform into a true enterprise migration system by grounding feature progress in foundational readiness, providing clear blocker visibility, and streamlining developer review.
