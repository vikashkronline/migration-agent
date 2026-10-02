# Migration Agent Documentation Index

Welcome to the **Migration Agent Documentation**. This index is organized by stakeholder persona (**Project Owners**, **Architects & Tech Leads**, and **Developers & Engineers**) to help you quickly find the exact guides, technical references, and architectural specifications you need.

---

## 🧭 Navigation by Persona

```mermaid
flowchart TD
    Index["docs/index.md\nDocumentation Hub"]

    subgraph Owners ["Project Owners & Decision Makers"]
        O1["Executive Overview & Value"]
        O2["docs/capabilities.md\nFeatures & Framework Support"]
        O3["docs/threat-model.md\nData Safety & Risk Containment"]
    end

    subgraph Architects ["Architects & Tech Leads"]
        A1["docs/architecture.md\nInward Dependency Architecture"]
        A2["docs/learning-log.md\nArchitectural Decisions & Invariants"]
        A3["docs/phase-status.md\nQuality Gate & Test Verification"]
        A4["docs/roadmap.md\nPhased Evolution & Milestones"]
    end

    subgraph Developers ["Developers & Engineers"]
        D1["docs/user-guide.md\nEnd-to-End User Guide & CLI"]
        D2["Web GUI Control Center (agent ui)"]
        D3["Contextual Q&A (agent ask)"]
    end

    Index --> Owners
    Index --> Architects
    Index --> Developers
```

---

## 1. For Project Owners & Decision Makers

If you are evaluating the platform, assessing risk, or managing migration timelines:

- **[Platform Capabilities & Matrix](capabilities.md)**:
  Comprehensive catalog of supported source frameworks (Ember.js, AngularJS), target architectures (modern Angular 17+ through 21+ Standalone), full-stack discovery (FastAPI, Flask, Express, SQL), and semantic evaluation metrics.
- **[Safety, Invariants & Zero-Risk Guarantees](threat-model.md)**:
  Detailed threat model and security invariants explaining why source code is treated as strictly read-only, how staging sandboxes prevent corruption, and how automated rollbacks guarantee zero data loss.
- **[Project Roadmap & Evolution](roadmap.md)**:
  The phased milestone history documenting the progression from core discovery to semantic transformation, diagnostic self-repair, and unified pipeline orchestration.

---

## 2. For Enterprise Architects & Technical Leads

If you are designing migration workflows, establishing governance, or auditing platform mechanics:

- **[System Architecture](architecture.md)**:
  Inward dependency architecture, ports and adapters (Hexagonal), 4-tier storage topology (Git `.agent/`, SQLite operational state, JSONL audit mirror), and cryptographic approval binding (RFC 8785 canonical digests).
- **[Architectural Decisions & Learning Log](learning-log.md)**:
  Chronological record of every architectural decision, security invariant (Invariants 1–28), and engineering lesson across all 15 implementation phases.
- **[Phase Verification & Quality Gates](phase-status.md)**:
  Detailed audit logs and test evidence for every phase, confirming 100% green compliance across 345+ unit, contract, and integration tests, strict mypy type checking, and ruff linting.
- **[ADR-8 Controlled Apply Protocol](architecture.md#staging-workspace--controlled-apply-protocol-adr-8)**:
  The formal 4-step apply protocol: worktree drift verification $\to$ preflight path containment $\to$ backup diff snapshots $\to$ atomic patch application $\to$ postcondition validation $\to$ verified rollback.

---

## 3. For Developers & Migration Engineers

If you are actively running migrations, reviewing diffs, or troubleshooting code:

- **[Complete User Guide & CLI Reference](user-guide.md)**:
  Step-by-step practical guide covering all CLI commands:
  - `agent doctor`: Local setup and dependency health check.
  - `agent inventory` / `agent adopt`: Discovery and Git-native `.agent/` scaffolding.
  - `agent preview` / `agent stage` / `agent apply`: Low-level surgical workflow.
  - `agent migrate`: Unified, end-to-end orchestrated pipeline.
  - `agent validate`: Running compiler, test, and linter gates.
  - `agent ask`: Contextual technical Q&A with citation verification.
  - `agent decision` / `agent learning`: Recording ADRs and promoting solutions.
  - `agent eval --semantic`: Running semantic benchmarks against synthetic fixtures.
- **[Local Control Center Web UI](user-guide.md#local-control-center-web-gui-agent-ui)**:
  How to launch and use the browser-based dashboard on loopback (`http://127.0.0.1:8080`) for visual plan inspection, interactive step approval, and dependency graph visualization.

---

## 📚 Master Document Catalog

| Document | Primary Audience | Description |
|---|---|---|
| **[index.md](index.md)** | All | Central documentation index and navigation map. |
| **[user-guide.md](user-guide.md)** | Developers, Engineers | Practical step-by-step guide, command reference, and workflows. |
| **[capabilities.md](capabilities.md)** | Owners, Architects | Full framework matrix, target standards, and self-repair capabilities. |
| **[architecture.md](architecture.md)** | Architects, Leads | Hexagonal architecture, ports/adapters, storage, and security protocols. |
| **[learning-log.md](learning-log.md)** | Architects, Developers | In-depth log of architectural decisions, invariants, and learnings. |
| **[phase-status.md](phase-status.md)** | Leads, Auditors | Implementation status, test suites, and quality gate evidence. |
| **[threat-model.md](threat-model.md)** | Security, Architects | Risk analysis, isolation boundaries, and fail-closed security invariants. |
| **[roadmap.md](roadmap.md)** | Owners, Leads | Project progression across Phases 0 through 15. |
