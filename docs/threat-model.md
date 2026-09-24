# Threat Model

## Phase 2 scope

The analysis command executes a read-only agent to interpret the Phase 1 deterministic inventory.
Model outputs are untrusted data. Repository source files remain read-only. Phase 2 does not execute
repository code, spawn unapproved shell commands, modify source files, or inspect environment secrets.

## Protected assets

- Source repository bytes and metadata
- Secret material that may be present in or near a repository
- Files outside the selected repository root
- Files outside the explicitly selected report directory
- The integrity and reproducibility of inventory evidence
- Model prompt payloads and local execution privacy

## Trust boundaries

1. CLI arguments enter the application as untrusted paths, provider, and model names.
2. The filesystem adapter crosses into an untrusted repository tree.
3. Eligible bounded text enters deterministic manifest and framework parsers.
4. Typed inventory data crosses into the agent tools and LLM prompt.
5. Model outputs enter as untrusted structured JSON requiring schema and evidence validation.
6. Only the report writer may write, and only beneath a non-overlapping output root.

## Threats and current mitigations

| Threat | Mitigation |
| --- | --- |
| Path traversal outside the repository | Resolve the selected root and every eligible entry; reject entries that are not contained by the resolved root. |
| Symlink, junction, or reparse-point escape | Do not follow any such entry; count it without reporting its path. Use `O_NOFOLLOW` where the host provides it. |
| Source mutation | The filesystem adapter exposes inspection only and opens eligible files read-only. The agent has no write or command tools. Reports must be outside the source tree. |
| Secret discovery or disclosure | Skip secret-like names before content reads and report only aggregate counts. Do not inspect environment variables in tools. Excluded secrets never reach agent context. |
| Binary-parser confusion | Reject NUL-containing and non-UTF-8 eligible files before parsing. |
| Resource exhaustion from large files | Enforce a configurable per-file byte limit before and during reads. Ignore known dependency, VCS, cache, and build directories. |
| Non-deterministic evidence | Sort traversal results, dependencies, boundaries, issues, fingerprints, and JSON keys; omit timestamps. |
| Malformed manifests | Parse as data, never execute; record a typed non-fatal issue. |
| Output redirection into source | Reject output roots that contain, equal, or are contained by the source root. Use fixed report filenames and atomic replacement. |
| Hallucinated or invented evidence | Application service audits all evidence paths against deterministic inventory; invalid paths are marked `not_in_inventory` and confidence is penalized. |
| Prompt injection via source files | Agent is strictly read-only with no shell, write, network, or env-variable tools; tools read only pre-validated eligible snapshot files. |
| Context bloat / LLM loop DoS | Bound tool output characters (`max_tool_chars`), bound file read line count, and enforce maximum agent turns (`max_turns`). |
| Unintended telemetry / trace leakage | Disable remote trace export in OpenAI Agents SDK by default across local runs and tests. |

## Residual risks and deferred controls

- The source tree is not snapshotted, so another process can change ordinary files during
  inspection. Unix hosts use `O_NOFOLLOW`; Windows link checks cannot fully eliminate a
  hostile time-of-check/time-of-use race. Later isolated workspace support should operate
  on an immutable source identity or snapshot.
- File classification and secret-name rules are intentionally conservative but cannot
  recognize every organization-specific secret convention. A later policy layer can add
  configured patterns without weakening the default exclusions.
- Report metadata includes the user-selected repository root and dependency names. Reports
  must be treated as internal artifacts until a later redaction and retention policy is
  implemented.
- Phase 1 does not authenticate repository ownership or verify Git object integrity.
- Denial of service through extremely large directory counts is not yet globally budgeted;
  only directory exclusions and per-file limits exist in this phase.
