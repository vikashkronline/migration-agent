# Threat Model

## Phase 3 scope

The planning subsystem converts Phase 1 inventory and Phase 2 analysis findings into an ordered,
typed migration plan. Operations remain strictly read-only with respect to source repository code.
Phase 3 introduces Git governance in `.agent/`, SQLite operational state in `checkpoints.db`,
JSONL audit logging in `audit.jsonl`, RFC 8785 canonical metadata digests, and `ApprovalSignature`
cryptographic binding.

## Protected assets

- Source repository bytes and application code (strictly untouched)
- Secret material that may be present in or near a repository
- Integrity of migration plans, step sequences, and validation requirements
- Integrity and cryptographic binding of approval signatures
- Platform safety policies defined in `.agent/policy.json`
- Append-only audit trail and checkpoint state

## Trust boundaries

1. CLI arguments enter the application as untrusted paths, actor identities, and command flags.
2. Model planning output enters as untrusted structured JSON requiring schema and rule-based validation.
3. `.agent/` directory in target repository stores durable Git governance assets.
4. Local SQLite database (`checkpoints.db`) and `audit.jsonl` store local operational state.
5. Approval signatures bind actors to immutable plan content digests and policy digests.

## Threats and current mitigations

| Threat | Mitigation |
| --- | --- |
| Path traversal outside the repository | Resolve the selected root and every eligible entry; reject entries that are not contained by the resolved root. |
| Symlink, junction, or reparse-point escape | Do not follow any such entry; count it without reporting its path. Use `O_NOFOLLOW` where the host provides it. |
| Source mutation | The filesystem adapter exposes inspection only and opens eligible files read-only. The agent has no write or command tools. Reports and staging remain separate from source. |
| Secret discovery or disclosure | Skip secret-like names before content reads and report only aggregate counts. Do not inspect environment variables in tools. Excluded secrets never reach agent context. |
| Hallucinated or invented evidence | Application service audits all evidence paths against deterministic inventory; invalid paths are marked `not_in_inventory` and confidence is penalized. |
| Stale or tampered plan approval | Approvals are bound via RFC 8785 canonical JSON metadata hashing over plan content (`plan_digest`) and policy (`policy_digest`). Any mutation to steps, files, or policy invalidates the signature (`verify_approval()` returns `False`). |
| Dependency cycles / Infinite execution loops | `RuleBasedPlanValidator` enforces Directed Acyclic Graph (DAG) cycle detection using Kahn's algorithm and rejects plans with circular dependencies. |
| Unvalidated or unchecked transformation steps | Validator requires every step to define a non-empty `validation_strategy`; steps lacking validation are rejected. |
| Overly complex / monolithic migration steps | Validator enforces maximum expected file thresholds per step (`max_step_files`) to bound transformation blast radius. |
| Unauthenticated / unauthorized approval (Mode C) | Mode C (unauthenticated / inspection) is strictly forbidden from approving migration plans in both CLI and domain logic. |
| Database SQL injection | `SqliteCheckpointStore` exclusively uses parameterized queries and prepared statements for all database operations. |
| Path traversal via `.agent/` exports | `GitGovernanceAdapter` validates that `.agent/` and `.agent/plans/` paths are strictly contained within the resolved project root. |

## Residual risks and deferred controls

- The source tree is not snapshotted, so another process can change ordinary files during
  inspection. Later isolated workspace support (Phase 4) operates on worktrees and staging copies.
- File classification and secret-name rules are intentionally conservative but cannot
  recognize every organization-specific secret convention.
- Mode A (cryptographically verified SSH/GPG keys) currently records identity fingerprints;
  integration with native ssh-agent/gpg binaries is expanded in later phases.
- Phase 3 does not yet execute code transformation or validation test runners (deferred to Phases 4 & 5).
