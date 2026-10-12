# Migration Agent User Guide

For owner-approved runtime profiles, personal model choices, environment paths and configuration
checks, open **Control Center → Settings** or run `agent config --help`. The
[configuration guide](project-configuration.md) documents eligible roles, exact owner activation,
root handoffs and interrupted-operation recovery. Settings changes do not start workflows.

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

For a separate migration acceptance project with a strictly read-only original,
use `agent init <external-project> --source <source> --state-dir <external-state>
--staging-root <external-staging>`. Record decisions in the external project and
pass it as `plan create --output`; continue passing state/staging flags explicitly.
See [separate initialization and readiness limits](end-user-acceptance-hardening.md).

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
- `--auto-approve`: Approves the high-level plan only; exact ChangeSet approval still requires human review.
- `--allow-dirty`: A legacy inspection override; the shared live workflow requires a clean Git base.
- `--max-repairs <n>`: Bounds live repair attempts from zero to ten (default: 3).
- `--skip-validation`: Allows scratch staging but cannot authorize source apply.

### Guarded Migration Sequence:
```text
$ uv run agent migrate /path/to/legacy-repo

[Preflight] Validating repository structure and Git status...
[Plan] Generating migration DAG (3 steps discovered)...
  - step-001: Initialize modern package dependencies (scope: dependency, risk: low)
  - step-002: Migrate UserCard to Angular Standalone (scope: component, risk: medium)
  - step-003: Migrate UserList to Angular Standalone (scope: component, risk: medium)

[Prompt] Approve this high-level plan? [y/N]: y
[Staging] Materializing one supported component/service step in an isolated sandbox...
[Validation] Running tsc and test validation gates... Passed!
[Stop] Exact ChangeSet human approval required.
```

This is an illustrative sequence, not a captured terminal transcript. Use the
returned plan/step/ChangeSet IDs with `agent review`, interactive `agent approve`,
then `agent apply`. The complete commands and external roots are in
[Phase 16 client setup and operation](phase-16-client-setup.md).

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
uv run agent stage /path/to/legacy-repo --plan <plan_id> --step step-002 --state-dir <state> --staging-root <staging>
```
Materializes the code in the isolated staging sandbox (`.staging-root/`).

### 6. Validate in Staging
```bash
uv run agent validate /path/to/legacy-repo --plan <plan_id> --step step-002 --profile ALL --state-dir <state> --staging-root <staging>
```

### 7. Apply with ADR-8 Protocol
```bash
uv run agent review step-002 --project-root /path/to/legacy-repo --plan <plan_id> --state-dir <state> --staging-root <staging>
uv run agent approve step-002 --project-root /path/to/legacy-repo --plan <plan_id> --state-dir <state> --staging-root <staging>
uv run agent apply /path/to/legacy-repo --plan <plan_id> --changeset <changeset_id> --state-dir <state> --staging-root <staging>
```
Executes preflight containment, backup snapshot creation, patch application, and postcondition verification.

---

## 6. Local Control Center Web GUI (`agent ui`)

The implemented common GUI uses the same external workflow state as CLI/MCP.
Use it for navigation, evidence inspection and guarded action requests. Exact
human approval remains in the trusted terminal.

For team members, reviewers, or architects who prefer a graphical interface:

```bash
uv run agent ui /path/to/legacy-repo
```

- Binds strictly to the loopback interface (`http://127.0.0.1:8080`).
- Automatically launches your default web browser.
- Project hierarchy, bounded search, attention filtering and recorded task totals.
- Mobile navigation drawer, stable history and artifact-bound decision links.
- Checks, proposed file contents, operation diagnostics and on-demand screenshots.
- In Artifacts, **Open read-only diff** provides changed-file search, numbered
  unified/split base/proposal views and basic code colouring. Mobile uses unified
  view; unavailable or oversized files have explicit feedback. No source editing,
  comments or approval is performed by this viewer.
- Strict architecture diagrams and bounded governance references.
- Stage/validate/exact apply through existing guarded services, with external IDE
  review and human-terminal approval handoff.

Select the same `--state-dir` and `--staging-root` as the existing workflow.
Optional [Git-owned project work](project-work.md) supplies foundation/module
scope linked to existing evidence; unknown readiness stays explicit. Ask returns
cited recorded facts, with broader reasoning handed off to the CLI/host. See
[Control Center operations and limits](control-center.md).

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
| `agent stage` | Materialize a step through shared gates | `--plan`, `--step`, `--state-dir`, `--staging-root` |
| `agent validate` | Record real backend validation provenance | `--plan`, `--step`, `--profile` |
| `agent review` / `agent approve` | Exact artifact review / human confirmation | `--project-root`, `--plan`, `--state-dir`, `--staging-root` |
| `agent apply` | Execute guarded exact ChangeSet apply | `--plan`, `--changeset`, `--state-dir`, `--staging-root` |
| `agent submit-repair` | Submit a bounded external repair proposal | `--project-root`, `--request-id` |
| `agent recover` | Verify completed target or restored base | `--project-root`, `--plan` |
| `agent mcp setup` | Preview/write client stdio configuration | `--client`, `--project-root`, `--config`, `--write` |
| `agent ui` | Launch Local Control Center Web GUI on 127.0.0.1 | `--port`, `--no-open`, `--state-dir`, `--staging-root` |
| `agent ask` | Contextual Q&A bounded by inventory & ADRs | `--provider`, `--model`, `--fake-runtime` |
| `agent decision` | Record and list Architectural Decision Records | `record`, `list` |
| `agent eval` | Run benchmark evaluations against synthetic fixtures | `--semantic`, `--adapter` |

## Phase 16 host and standalone workflow

Follow [client setup and operation](phase-16-client-setup.md). Source repositories stay read-only through proposals, staging, validation, and approval creation. Only the guarded apply path writes approved exact artifacts. Missing policy-accepted backend evidence blocks approval. Plan auto-approval and skipped/fake checks do not authorize apply. Live host smoke results are tracked separately in [acceptance checklists](phase-16-smoke-checklists.md).

## Native execution consent

Follow [native operations](native-validation.md) to select and provision validation
on Windows without Docker/WSL. After staging, the human runs `agent validation
authorize`; this grants execution permission only. Then validate, optionally resume
the saved step with `agent validation repair`, review, separately approve, and apply.

## Required browser UI/UX review

Run shared validation with all command profiles before browser inspection. Configure
the coverage/rule plan, inspect actual screenshots as a UI/UX specialist and submit
complete case/rule verdicts through the host tools or CLI browser commands. Every
repair requires new capture/review. Optional source comparison uses an authorized
read-only reference runtime; optional E2E runs last. See [browser operations](browser-ui-ux-validation.md)
for setup, commands, limits and the opt-in standalone OpenAI/Gemini visual adapter.
`agent validation status` reports backend/consent; `revoke` stops outstanding
validation at its heartbeat. Models must never automate the human confirmation.

## Completed common Control Center

Launch `uv run agent ui /path/to/project` with the same external state and staging
roots used by your workflow. Use the project tree for foundation, modules and
knowledge; select a group for its progress dashboard or a task for evidence and
actions. Mobile navigation opens from **Project navigation** and closes after
selection. Section links and browser history retain the selected artifact context.

Optionally maintain [.agent/project-work.json](project-work.md) in the source Git
repository before staging. It defines your own hierarchy, owners, acceptance
criteria and links to existing workflow records. Declarations alone never imply
verified readiness. Ask returns selected recorded facts with citations; broader
reasoning and human approval use the displayed CLI handoffs. Full code review
continues in your IDE. See [GUI operations](control-center.md).

After staging a step, use `agent validation standards` to inspect its rule coverage
against the opt-in technical standards profile. The report identifies machine-check
results, required recorded validation and pending semantic review. It preserves
the existing source approval workflow. See [usage and report meanings](standards-review.md).

Before governed writes, enroll the owner through `agent access bootstrap` and the
trusted-terminal signature handoff. Open **Users and access** to prepare member,
role, ownership and Git-connection changes. Git users remain pending until their
agent identity is enrolled. [RBAC setup and operations](rbac-and-users.md) documents
the required separate roots, signing keys and remote Git enforcement.
