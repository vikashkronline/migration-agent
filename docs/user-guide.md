# Migration Agent User Guide

The **Migration Agent** (`agent` / `migration-agent`) is a controlled, evidence-based migration workbench. It transforms legacy web applications (Ember.js, AngularJS) into modern Angular (17+ through 21+ Standalone with Signals) using isolated staging sandboxes, cryptographic approval gates, automated self-repair, and verified rollbacks.

---

## Table of Contents

1. [Prerequisites & System Setup](#1-prerequisites--system-setup)
2. [Quickstart: Health Check](#2-quickstart-health-check)
3. [Adopting an Existing Project](#3-adopting-an-existing-project)
4. [The Unified Migration Pipeline (`agent migrate`)](#4-the-unified-migration-pipeline-agent-migrate)
5. [Granular Step-by-Step Workflow](#5-granular-step-by-step-workflow)
6. [Local Control Center Web GUI (`agent ui`)](#6-local-control-center-web-gui-agent-ui)
7. [Contextual Technical Q&A (`agent ask`)](#7-contextual-technical-qa-agent-ask)
8. [Governance: ADRs & Curated Knowledge](#8-governance-adrs--curated-knowledge)
9. [Semantic Evaluation Benchmarking (`agent eval`)](#9-semantic-evaluation-benchmarking-agent-eval)
10. [CLI Command Reference Summary](#10-cli-command-reference-summary)

---

## 1. Prerequisites & System Setup

Ensure your development environment meets the following requirements:

| Dependency | Minimum Version | Purpose |
|---|---|---|
| **Python** | 3.12+ | Core migration platform runtime |
| **`uv`** | Latest | High-performance Python package and venv runner |
| **Git** | 2.30+ | Working tree clean checks, history, and backups |
| **Node.js & npm** | 18.x+ (Recommended 20.x+) | Running validation gates (`tsc`, Angular tests) |

### Installation

Clone the repository and synchronize the environment:
```bash
git clone <repository-url> migration-agent
cd migration-agent
uv sync --all-groups
```

> [!NOTE]
> The agent has two symmetrical binary names: `agent` (canonical) and `migration-agent` (alias). When working directly inside the cloned repository, run commands prefixed with `uv run agent <command>`.

---

## 2. Quickstart: Health Check

Verify that all local runtimes, package dependencies, and tools are functioning:
```bash
uv run agent doctor
```

**Sample Output:**
```json
{
  "checks": [
    {"name": "python", "status": "pass", "details": {"actual": "3.12.14", "minimum": "3.12"}},
    {"name": "runtime_dependencies", "status": "pass", "details": {"pydantic": "2.13.5", "typer": "0.27.2", "google-genai": "2.25.0", "openai-agents": "0.22.3"}},
    {"name": "model_configuration", "status": "pass", "details": {"configured": false, "required_for_doctor": false}}
  ],
  "schema_version": 1,
  "status": "ok"
}
```

---

## 3. Adopting an Existing Project

Before running migrations on an existing legacy repository (Ember or AngularJS), adopt the project to scaffold the Git-native `.agent/` governance structure and generate architecture diagrams:

```bash
uv run agent adopt /path/to/legacy-repo
```

This command performs:
1. Deterministic filesystem inventory without modifying source code.
2. Cross-domain dependency graph discovery (frontend components, backend APIs, SQL tables).
3. Creation of `.agent/` directory containing:
   - `.agent/manifest.json`: Platform version and project metadata.
   - `.agent/policy.json`: Security rules and protected paths.
   - `.agent/config.json`: Local configuration defaults.
   - `.agent/architecture.md`: Human-readable architectural summary with Mermaid diagrams.

---

## 4. The Unified Migration Pipeline (`agent migrate`)

The `agent migrate` command coordinates the entire end-to-end migration lifecycle in one unified execution:

```bash
uv run agent migrate /path/to/legacy-repo
```

### Common Flags:
- `--dry-run`: Previews the migration plan, generated files, and diffs without staging execution or disk writes.
- `--step <step-id>`: Migrates only a specific plan step (e.g. `step-001`), keeping reviews granular.
- `--auto-approve`: Automatically approves the migration plan without interactive terminal prompts (ideal for CI/CD).
- `--allow-dirty`: Bypasses Invariant 25 (clean Git working tree requirement) for local testing.
- `--max-repairs <n>`: Specifies maximum self-repair attempts if compilation fails (default: 3).
- `--skip-validation`: Bypasses `tsc` and test execution gates if testing dependencies are not locally installed.

### Typical Interactive Migration Session:
```text
$ uv run agent migrate /path/to/legacy-repo

[Preflight] Validating repository structure and Git status...
[Plan] Generating migration DAG (3 steps discovered)...
  - step-001: Initialize modern package dependencies (scope: dependency, risk: low)
  - step-002: Migrate UserCard to Angular Standalone (scope: component, risk: medium)
  - step-003: Migrate UserList to Angular Standalone (scope: component, risk: medium)

[Prompt] Approve and apply this plan? [y/N]: y
[Staging] Materializing step-001 in isolated staging sandbox...
[Validation] Running tsc and test validation gates... Passed!
[Apply] Creating byte-level backup snapshot...
[Apply] Applying changes to source tree with file mode preservation...
[Apply] Postcondition verification passed!

[Report] Migration summary written to migration-summary.md
```

---

## 5. Granular Step-by-Step Workflow

For fine-grained, surgical control, you can execute individual phases manually:

### 1. Create a Plan
```bash
uv run agent plan create /path/to/legacy-repo --provider gemini --model gemini-2.5-pro
```
*Note: Add `--fake-runtime` to run 100% offline without API keys.*

### 2. Inspect the Plan
```bash
uv run agent plan show <plan_id>
```

### 3. Approve the Plan
```bash
uv run agent plan approve <plan_id> --actor "engineer@company.com"
```

### 4. Preview the Changes (Diff Inspection)
```bash
uv run agent preview /path/to/legacy-repo --step step-002 --output ./preview/
```
Generates `changeset.json` and `preview.diff` for code review.

### 5. Stage the Code
```bash
uv run agent stage /path/to/legacy-repo --step step-002
```
Materializes the code in the isolated staging sandbox (`.staging-root/`).

### 6. Validate in Staging
```bash
uv run agent validate <staging_path> --profile test
```

### 7. Apply with ADR-8 Protocol
```bash
uv run agent apply /path/to/legacy-repo --changeset-file ./preview/changeset.json
```
Executes preflight containment, backup snapshot creation, patch application, and postcondition verification.

---

## 6. Local Control Center Web GUI (`agent ui`)

For team members, reviewers, or architects who prefer a graphical interface:

```bash
uv run agent ui /path/to/legacy-repo
```

- Binds strictly to the loopback interface (`http://127.0.0.1:8080`).
- Automatically launches your default web browser.
- **Features**:
  - Interactive Dependency Graph (visualizing components and services).
  - Step Approval Dashboard with diff views.
  - Active Run Monitoring & Live Diagnostic Logs.
  - Curated Learnings and ADR inspection.

---

## 7. Contextual Technical Q&A (`agent ask`)

Ask targeted architectural or technical questions bounded strictly by your project's code, ADRs, and curated learnings:

```bash
uv run agent ask /path/to/legacy-repo "Which Ember components have complex action hierarchies?"
```

- **Zero Hallucination Guarantee**: The agent searches only eligible files in the project inventory.
- **Audited Citations**: All cited file paths are cross-checked against the inventory; hallucinated files are stripped and annotated.

---

## 8. Governance: ADRs & Curated Knowledge

Manage durable architectural decisions and solutions directly within `.agent/`:

### Record an Architectural Decision Record (ADR):
```bash
uv run agent decision record \
  --id "ADR-002" \
  --title "UI Component Library Strategy" \
  --context "Modernizing legacy Ember components to Angular 18+." \
  --decision "Adopt Angular Material (@angular/material) for all standard form controls." \
  --consequences "Templates will render mat-button and mat-card components." \
  --by "tech-lead"
```

### List Recorded ADRs:
```bash
uv run agent decision list /path/to/legacy-repo
```

### Record a Challenge & Solution:
```bash
# Record an encountered migration challenge
uv run agent challenge record --id CH-001 --category "DI" --title "Implicit Service Injections"

# Propose a candidate solution
uv run agent solution propose --id SOL-001 --challenge-id CH-001 --strategy "Inject Service via inject()"

# Promote to curated learning (requires human approval ID)
uv run agent learning approve --id LRN-001 --solution-id SOL-001 --approved-by "lead-architect"
```

---

## 9. Semantic Evaluation Benchmarking (`agent eval`)

Measure migration transformation quality using the built-in evaluation harness:

```bash
uv run agent eval --semantic
```

### Metrics Evaluated:
- **`compilation_pass_rate`**: Validates syntax balance, braces/parentheses integrity, and valid TypeScript declarations across generated code.
- **`spec_pass_rate`**: Measures Jasmine/Jest unit test completeness (`describe`, `it`, `expect`, `TestBed`).
- **`control_flow_fidelity`**: Measures the ratio of modern Angular 17+ control flow blocks (`@if`, `@for`, `@switch`) versus legacy directives (`ng-*`, `*ngIf`).

---

## 10. CLI Command Reference Summary

| Command | Purpose | Key Flags |
|---|---|---|
| `agent doctor` | Check environment, dependencies, and health | `--json` |
| `agent inventory` | Build deterministic file & framework inventory | `--output`, `--json` |
| `agent adopt` | Initialize `.agent/` and generate architecture diagrams | `--allow-dirty` |
| `agent migrate` | **Unified end-to-end migration pipeline** | `--dry-run`, `--step`, `--auto-approve`, `--allow-dirty`, `--max-repairs` |
| `agent plan` | Create, show, approve, or reject migration DAGs | `create`, `show`, `approve`, `reject` |
| `agent preview` | Generate proposed ChangeSet and unified diff | `--step`, `--output` |
| `agent stage` | Materialize ChangeSet in isolated staging sandbox | `--step`, `--changeset-file` |
| `agent validate` | Execute allowlisted test/lint/typecheck commands | `--profile` |
| `agent apply` | Execute ADR-8 4-step controlled apply protocol | `--changeset-file`, `--actor` |
| `agent ui` | Launch Local Control Center Web GUI on 127.0.0.1 | `--port`, `--no-open` |
| `agent ask` | Contextual Q&A bounded by inventory & ADRs | `--provider`, `--model`, `--fake-runtime` |
| `agent decision` | Record and list Architectural Decision Records | `record`, `list` |
| `agent eval` | Run benchmark evaluations against synthetic fixtures | `--semantic`, `--adapter` |
