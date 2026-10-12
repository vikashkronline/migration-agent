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
| Staging path escape / traversal | `LocalWorkspaceAdapter` strictly validates that staging directories reside within resolved `staging_root`. |
| Staging overlap with source repo | `LocalWorkspaceAdapter` rejects staging workspaces that are identical to or nested inside the source repository. |
| Symlink escape during staging copy | Filesystem walker skips symlinks pointing outside the source tree during staging workspace creation. |
| Unapproved or tampered apply | `TransformationService.apply` re-validates plan approval and cryptographic digest before modifying any file. |
| Target repository drift attack | Deterministic SHA-256 worktree fingerprinting verifies identical base state before applying; any drift enters `BaseChanged` and aborts. |
| Partial apply failure | ADR-8 backup snapshots capture prior file contents before mutation; apply failure triggers verified rollback (`RolledBack`). |
| Corrupted / unverified rollback | Double fault explicitly transitions to `RecoveryRequired`, halting automated operations and recording detailed diagnostic context for operator intervention. |
| Model-generated shell injection | Never execute raw model shell commands; allowlist strictly limits executables (`git`, `node`, `npm`, `npx`, `ng`, `tsc`, `pytest`, `python`, `uv`), uses `shell=False`, and rejects shell metacharacters (`;`, `&&`, `|`, `` ` ``, `$`, `\n`) in arguments. |
| Subprocess working directory escape | `SubprocessCommandRunner` verifies working directory is confined within allowed root; escapes return `DISALLOWED`. |
| Credential disclosure via environment | Subprocess environment is actively sanitized by stripping all environment variables containing `KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`, `AUTH`, `OPENAI`, `GEMINI`. |
| Subprocess hanging / denial of service | All commands run with bounded timeouts (`timeout_seconds`, default 60s); timeouts trigger SIGKILL and transition to `TIMED_OUT`. |
| Log flooding / terminal resource exhaustion | Command output is capped at `max_output_bytes` (64KB); overflow appends `... [TRUNCATED]` while full SHA-256 digest is preserved for verification. |
| Infinite self-repair loop | Invariant 26 limits repair loop to max 3 attempts; repeated identical failures immediately terminate early without wasting budget. |
| Scope expansion attack during repair | Invariant 26 validates candidate repair ChangeSets against approved step scope; modifying unapproved files halts loop with `DISALLOWED`. |
| Secret disclosure in audit logs | `RedactionPolicy` recursively cleans dictionary keys matching sensitive substrings (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`, `AUTH`, `OPENAI`, `GEMINI`) and redacts inline token patterns before writing to SQLite and `audit.jsonl`. |
| Unbounded log disk exhaustion | Payloads > 512 bytes are digested with SHA-256 and truncated, preserving full content digests without bloat. |
| Retrospective audit tampering or clock skew | `verify_audit_log` uses SQLite physical insertion order (`rowid`) to guarantee strict monotonic chronological integrity. |
| Repair budget evasion across crashes | Resumption checks prior `REPAIR_ATTEMPT` checkpoints to decrement remaining budget, preventing budget reset attacks. |
| Stale staging workspace reuse | Resumption verifies staging directory integrity, plan approval, and applied changeset digest before skipping staging. |

## Residual risks and deferred controls

- File classification and secret-name rules are intentionally conservative but cannot
  recognize every organization-specific secret convention.
- Mode A (cryptographically verified SSH/GPG keys) currently records identity fingerprints;
  integration with native ssh-agent/gpg binaries is expanded in later phases.
- Specialist multi-agent role decomposition and evaluation-driven subagents are deferred to Phase 8.


## Native validation trust boundary

Native is explicitly trusted account execution, not a kernel filesystem or egress
sandbox. Positive environments and staging fingerprints reduce accidental exposure
and detect input drift; they do not remove account permissions. Windows jobs
supervise inherited descendants and kill on supervisor handle close; services
outside the job remain outside that guarantee. Linux group supervision differs.
Unsupported strict controls fail closed. Human consent binds the base, policy,
fixed profiles, installed toolchain/dependencies and bounded repair scope; separate
exact source approval remains mandatory. Mode B retains same-account limitations;
Mode A checks an active external authority. [Precise limits](native-validation.md).

## Browser validation boundaries

Page content and AI visual verdicts are untrusted. Captured PNG hashes, dimensions,
complete coverage, required rules and objective failures are checked deterministically.
Source/build/config/tool/consent drift invalidates browser evidence and approval.
Typed actions permit no arbitrary JavaScript/shell. Source reference navigation is
read-only; separately authorized synthetic backend fixtures use explicit loopback
origins. Screenshots can contain sensitive data: use non-secret synthetic cases.
Direct provider disclosure is disabled by default. The explicitly authorized adapter
requires trusted launcher opt-in and binds fixed destination/model/payload limits
into execution policy and native human consent. It preflights the complete export,
rejects recognized credential-shaped text and validates every image hash and rule
citation. These checks cannot recognize secrets in pixels or arbitrary prose; use
synthetic test cases. In-flight requests cannot be recalled on revocation. SDK errors
are sanitized, and complete reviews alone are persisted. Host UI review is not human source
approval. Native supervision retains account permissions; container worker mounts
preserve the existing isolation controls. [Operations](browser-ui-ux-validation.md).
