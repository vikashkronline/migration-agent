# RBAC R0 inventory and implementation decisions

Date: 2026-10-09

User authorization covers R0 through R6, including legacy containment, Git-member import and the owner GUI. No selected migration source is modified.

## Registered command/tool entry points

| File | Line | Registration | Name | Handler | Required boundary |
| --- | --- | --- | --- | --- | --- |
| `src/migration_agent/adapters/mcp/host_tools.py` | 43 | tool | `evidence_read` | `evidence_read` | evidence.read |
| `src/migration_agent/adapters/mcp/host_tools.py` | 54 | tool | `submit_analysis` | `submit_analysis` | analysis.submit |
| `src/migration_agent/adapters/mcp/host_tools.py` | 62 | tool | `submit_plan` | `submit_plan` | plan.submit |
| `src/migration_agent/adapters/mcp/host_tools.py` | 68 | tool | `submit_repair` | `submit_repair` | repair.submit |
| `src/migration_agent/adapters/mcp/host_tools.py` | 76 | tool | `operation_status` | `operation_status` | operation.read |
| `src/migration_agent/adapters/mcp/host_tools.py` | 134 | tool | `operation_cancel` | `operation_cancel` | operation.cancel |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 36 | tool | `stage` | `stage` | changeset.stage |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 42 | tool | `validate` | `validate` | validation.run |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 50 | tool | `request_review` | `request_review` | approval.request |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 73 | tool | `apply` | `apply` | changeset.apply |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 81 | tool | `browser_request` | `browser_request` | changeset.read |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 88 | tool | `browser_screenshot` | `browser_screenshot` | changeset.read |
| `src/migration_agent/adapters/mcp/mutation_tools.py` | 110 | tool | `browser_submit` | `browser_submit` | validation.review.submit |
| `src/migration_agent/adapters/mcp/server.py` | 162 | tool | `doctor` | `doctor` | system.diagnostics |
| `src/migration_agent/adapters/mcp/server.py` | 177 | tool | `inventory` | `inventory` | project.read |
| `src/migration_agent/adapters/mcp/server.py` | 198 | tool | `run_status` | `run_status` | run.read |
| `src/migration_agent/adapters/mcp/server.py` | 217 | tool | `plan_show` | `plan_show` | plan.read |
| `src/migration_agent/adapters/mcp/server.py` | 240 | tool | `step_preview` | `step_preview` | changeset.read |
| `src/migration_agent/adapters/mcp/setup.py` | 172 | command | `setup` | `setup` | platform-local controlled client configuration |
| `src/migration_agent/adapters/workflow_cli.py` | 121 | command | `standards` | `review_standards` | changeset.read |
| `src/migration_agent/adapters/workflow_cli.py` | 150 | command | `browser-request` | `browser_request` | changeset.read |
| `src/migration_agent/adapters/workflow_cli.py` | 169 | command | `browser-submit` | `browser_submit` | validation.review.submit |
| `src/migration_agent/adapters/workflow_cli.py` | 204 | command | `authorize` | `authorize_native` | validation.authorize (human-only) |
| `src/migration_agent/adapters/workflow_cli.py` | 312 | command | `revoke` | `revoke_native` | validation.authorize |
| `src/migration_agent/adapters/workflow_cli.py` | 330 | command | `repair` | `repair_native` | repair.submit |
| `src/migration_agent/adapters/workflow_cli.py` | 384 | command | `status` | `validation_status` | access.self.read |
| `src/migration_agent/adapters/workflow_cli.py` | 416 | command | `submit-repair` | `submit_repair` | repair.submit |
| `src/migration_agent/adapters/workflow_cli.py` | 447 | command | `recover` | `recover` | workflow.recover |
| `src/migration_agent/adapters/workflow_cli.py` | 506 | command | `review` | `review` | changeset.read |
| `src/migration_agent/adapters/workflow_cli.py` | 533 | command | `approve` | `approve` | approval.record (human-only) |
| `src/migration_agent/cli.py` | 191 | command | `doctor` | `doctor` | system.diagnostics |
| `src/migration_agent/cli.py` | 200 | command | `inventory` | `inventory_command` | project.read |
| `src/migration_agent/cli.py` | 268 | command | `graph` | `graph_command` | project.read |
| `src/migration_agent/cli.py` | 398 | command | `fullstack` | `fullstack_command` | project.read |
| `src/migration_agent/cli.py` | 497 | command | `analyze` | `analyze_command` | analysis.submit + provider.disclose when live |
| `src/migration_agent/cli.py` | 621 | command | `create` | `plan_create_command` | plan.submit + provider.disclose when live |
| `src/migration_agent/cli.py` | 825 | command | `show` | `plan_show_command` | plan.read |
| `src/migration_agent/cli.py` | 893 | command | `approve` | `plan_approve_command` | plan.approve (legacy Mode A disabled) |
| `src/migration_agent/cli.py` | 1091 | command | `reject` | `plan_reject_command` | plan.approve |
| `src/migration_agent/cli.py` | 1264 | command | `preview` | `preview_command` | changeset.read |
| `src/migration_agent/cli.py` | 1371 | command | `stage` | `stage_command` | changeset.stage |
| `src/migration_agent/cli.py` | 1434 | command | `apply` | `apply_command` | changeset.apply |
| `src/migration_agent/cli.py` | 1506 | command | `migrate` | `migrate_command` | composed per-step requirements |
| `src/migration_agent/cli.py` | 1717 | command | `validate` | `validate_command` | validation.run |
| `src/migration_agent/cli.py` | 1902 | command | `start` | `run_start_command` | composed per-step requirements |
| `src/migration_agent/cli.py` | 2112 | command | `list` | `run_list_command` | run.read |
| `src/migration_agent/cli.py` | 2145 | command | `show` | `run_show_command` | run.read |
| `src/migration_agent/cli.py` | 2193 | command | `resume` | `run_resume_command` | composed per-step requirements |
| `src/migration_agent/cli.py` | 2374 | command | `eval` | `eval_command` | platform-local fixed fixture evaluation |
| `src/migration_agent/cli.py` | 2497 | command | `ui` | `ui_command` | session resolution; each action separately authorized |
| `src/migration_agent/cli.py` | 2652 | command | `init` | `init_project` | inspection-only scaffolding, no owner grant |
| `src/migration_agent/cli.py` | 2730 | command | `adopt` | `adopt_project` | controlled governance initialization, source stays read-only |
| `src/migration_agent/cli.py` | 2795 | command | `record` | `record_challenge_command` | challenge.write |
| `src/migration_agent/cli.py` | 2830 | command | `list` | `list_challenges_command` | project.read |
| `src/migration_agent/cli.py` | 2846 | command | `record` | `record_solution_command` | solution.write |
| `src/migration_agent/cli.py` | 2888 | command | `list` | `list_solutions_command` | project.read |
| `src/migration_agent/cli.py` | 2904 | command | `approve` | `approve_learning_command` | learning.approve |
| `src/migration_agent/cli.py` | 2954 | command | `list` | `list_learnings_command` | project.read |
| `src/migration_agent/cli.py` | 2970 | command | `record` | `record_decision_command` | decision.write |
| `src/migration_agent/cli.py` | 3010 | command | `list` | `list_decisions_command` | project.read |
| `src/migration_agent/cli.py` | 3026 | command | `ask` | `ask_question` | evidence.read + provider.disclose when live |
| `src/migration_agent/cli.py` | 3093 | command | `spec` | `package_spec_command` | platform-local controlled artifact generation |
| `src/migration_agent/cli.py` | 3123 | command | `manifest` | `package_manifest_command` | platform-local controlled artifact generation |
| `src/migration_agent/cli.py` | 3179 | command | `verify` | `package_verify_command` | system.diagnostics |
| `src/migration_agent/cli.py` | 3221 | command | `cloak` | `package_cloak_command` | platform-local presentation utility, no authority |
| `src/migration_agent/cli.py` | 3233 | command | `decloak` | `package_decloak_command` | platform-local presentation utility, no authority |
| `src/migration_agent/cli.py` | 3245 | command | `serve` | `mcp_serve_command` | session resolution; each tool separately authorized |

## Accepted implementation baseline

The user instruction to proceed authorizes implementing the specified baseline: finite capability roles, verified principal bindings, genuine purpose-separated Ed25519/SSH proof, old-policy authorization, immutable access snapshots, disjoint external governance, strict lock ordering, explicit Git-provider identity mapping and owner administration with trusted-terminal signatures. Local Mode B never activates security-policy changes.

## Legacy verifier caller map

- Production implementation: `adapters/trust_store.py:CryptoSignatureVerifierAdapter`.
- Production constructor: `cli.py:plan_approve_command`; `PlanningService.approve_plan` invokes the injected verifier before persisting an approval.
- The current workbench refuses legacy browser action routes. Shared apply uses `LocalApprovalProof`, which remains independent and uses real Ed25519 verification.
- R0-C disables legacy signing and verification with terminal `SecurityConfigurationError`; CLI renders the failure and cannot downgrade/retry.

## Actual lock/lease baseline

- `ExclusiveApplyLock` is an OS-level nonblocking per-project apply lock shared across state directories.
- `LocalControlledFiles` takes per-mutation fence callbacks; it has no separate OS lock.
- Native validation owns a workflow writer lease and bounded child-process lifecycle, rather than the full apply OS lock.
- Access publication must use its separate lease namespace and strict access -> apply -> optional workspace -> lease -> transaction ordering.

## Additional scope from user clarification

- Import existing governance Git members from GitHub/GitLab through bounded read-only provider adapters; never infer identity from commit author/email.
- Bind provider hostname and immutable provider user ID to an enrolled principal and proof-bearing public/OS identity.
- Owner explicitly selects agent roles; Git maintainer status does not grant agent ownership.
- Governance publication verification must cover role, permission and security-rule bytes and must not trust verifier code changed by the incoming proposal.
- Remote Git push protection is a separate configured boundary; local agent RBAC cannot claim it is installed or enforced without server acceptance evidence.

## Execution status

R0-C containment implementation and verification are in progress. Later runtime milestones start only after the current milestone gates pass.

## HTTP/application enforcement inventory

| Existing boundary | Required enforcement |
| --- | --- |
| Authenticated workbench session/tree/detail/events/images/diffs | Scoped evidence/read capabilities; current identity/revision before cached/replayed results |
| Workbench command stage/validate/apply | Corresponding capability before receipt lookup and again at worker start/pre-write |
| Workbench question | Scoped recorded facts; no automatic provider disclosure |
| Legacy Control API routes | Reject alternate privileged routes; read endpoints require the same verified identity/project scope |
| HostProposalService | Evidence, analysis, plan, repair and cancellation capabilities, current repository binding |
| ApplyService | Stage/validate/review/approve/apply permissions; approver/executor separately current; source-base and execution gates retained |
| PlanningService / KnowledgeService | Public inspection preparation versus governed writes; no supplied actor string grants authority |
| Worker execution / callback fences | Current initiating principal and access digest; no token persistence; authorized compensating cleanup only |
| Provider tools | Check evidence before every read and explicit disclosure before SDK request |
| Governance publication verifier | Verify old independently anchored policy, complete role/rule hashes and exact signed change, never incoming verifier code |

The capability catalog and declared-action coverage tests added in R1/R3 must turn this reviewed map into runtime-enforced contracts. The baseline source line numbers are evidence references, not stable identifiers.


R0-C verification: terminal legacy containment passed 670 tests with 3 skips. All later user-management/RBAC milestones were explicitly authorized on 2026-10-09; consolidated implementation verification is recorded in rbac-implementation-report.md.
