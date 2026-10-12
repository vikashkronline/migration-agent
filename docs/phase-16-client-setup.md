# Phase 16 client setup and operation

Native validation is implemented as the Phase 16 amendment. Follow
[native validation operations](native-validation.md) for Windows without Docker/WSL,
human execution consent, offline provisioning, repair and backend selection.
Live host/operator acceptance remains separate from automated implementation tests.

## Install and preview

From the agent installation environment, run:

```text
uv sync --all-groups
uv run agent doctor
uv run agent mcp setup --client codex --project-root <absolute-source-root>
uv run agent mcp setup --client antigravity --project-root <absolute-source-root>
```

Preview emits only the proposed named entry, arguments, and destination. It creates
no client configuration, source files, or state directory. Add `--write` after
reviewing the preview. Existing files receive an exclusive backup and an atomic
replacement. JSON preserves unrelated settings and servers; TOML appends a new
server table while retaining existing comments/settings. An identical entry is a
no-op. An existing different Codex entry requires manual review/replacement.
Malformed, oversized, linked, concurrently modified, or credential-bearing files
fail closed. No existing configuration contents are printed. Use `--config` for
the configuration actually selected by the installed client, including older IDE
versions. No client files were installed in the operator's profile by this phase.

The default Codex destination is `~/.codex/config.toml`. Codex shares MCP
configuration across its CLI and IDE extension; configuration and stdio entry
format follow [OpenAI's MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
The current Antigravity general configuration destination is
`~/.gemini/config/mcp_config.json`; the entry uses `mcpServers`, `command`, `args`,
and `env` per [Google's MCP documentation](https://antigravity.google/docs/mcp).
Verify the actual IDE's **Manage MCP Servers → View raw config** destination;
older Antigravity IDE installations may use another location. This is documented
configuration compatibility, not evidence of a completed live IDE session.

Use `--state-dir` and `--staging-root` to choose disjoint external directories.
The source, state, staging, trust, and client configuration must not overlap
unsafely. Generated entries use the absolute installation interpreter and argument
arrays, preserving paths with spaces. The server remains usable from any client
working directory. Keep that installation environment available after setup.

Cursor JSON setup is available with `--client cursor`. Claude JSON setup requires
`--client claude --config <installed-client-config>` because CLI/Desktop locations
differ. Secondary client runtime compatibility remains unmeasured.

## Host instructions

The packaged `skills/migration-agent/SKILL.md` supports Antigravity and Codex.
Install it using the host's documented skill mechanism, outside the source under
migration. `plannings/codex-migration-agent-instructions.md` provides handoff and
installation guidance. Do not overwrite an existing source AGENTS.md.

The host supplies reasoning; the MCP server requires no separate model API key.
Use the configured standalone provider for `agent analyze` / `agent plan create`
or live `agent migrate`. `--fake-runtime`, `--fake-runner`, and dry-run artifacts
are development evidence and cannot authorize source apply.

Live `migrate` uses `--max-repairs` (zero to ten, default three) to bound repairs.
It tries recognized deterministic repairs, then typed diagnostic guidance from
the configured provider. Each candidate passes the host repair gate and receives
a new ChangeSet, stage, and validation execution. Repeated failures and unsupported
guidance stop; the command never signs or applies the resulting bytes. For a
manually prepared typed repair proposal, use:

```text
agent submit-repair <external-proposal.json> --project-root <source> --request-id <unique-id> --state-dir <state> --staging-root <staging>
```

The proposal must name the failed current ChangeSet and diagnostics digest and
contain only in-scope text replacements. Restage, revalidate, and obtain new human
approval after acceptance.

## Shared standalone workflow

```text
agent stage <source> --plan <plan-id> --step <step-id> --state-dir <state> --staging-root <staging>
agent validate <source> --plan <plan-id> --step <step-id> --state-dir <state> --staging-root <staging>
agent review <step-id> --project-root <source> --plan <plan-id> --state-dir <state> --staging-root <staging>
agent approve <step-id> --project-root <source> --plan <plan-id> --state-dir <state> --staging-root <staging>
agent apply <source> --plan <plan-id> --changeset <changeset-id> --state-dir <state> --staging-root <staging>
```

Select a single supported migration step. `migrate --auto-approve` signs off the
plan and stops for exact ChangeSet review; it does not authorize source writes.
`--skip-validation` cannot create apply eligibility. Plan dependencies and
unsupported constructs are checked before staging. After applying a step, review
and commit the changes and create a fresh plan for the new base; the server does
not commit on the user's behalf or silently rebase approvals.

For guarded apply, the positional source path establishes project identity, the
human approval record establishes the actor, and backups live under the external
state directory. In external-governance sessions, approved files publish only to
the separate target configured in Settings; that target and its exact base are
bound into approval. See [the current migration workflow](migration-workflow.md).
Legacy `--actor`, `--backup-root`, and apply `--project-root`
arguments remain compatibility parameters and do not override these bindings.

Container-selected production validation runs fixed templates inside Docker with a digest-pinned,
locally installed toolchain image supplied through `AGENT_VALIDATION_IMAGE`.
It uses no network, no pulls, a read-only root and staging bind mount, no extra
capabilities, a non-root user, and resource limits. The image must include the
project's required toolchain/dependencies. Install/build it through the operator's
trusted provisioning process. Missing isolation/toolchain or checks requiring
unconfigured writable output paths fail validation and block approval. There is
no automatic host subprocess fallback for MCP validation.

## Human approval and trust

`migration_request_approval` returns the full diff, exact digest, base/policy and
validation bindings, and human CLI command. It mints no approval. There is no
MCP `approve`, signer, bearer-token, or `auto_approve` endpoint. Tool permission
prompts in the host are independent of Migration Agent approval.

The human console displays the review and requires an exact digest confirmation.
Piped input and non-interactive sessions are rejected. Mode B is a local operator
assertion whose state directory and console are trusted. It is **not** a
cryptographic protection against a process with arbitrary access to the same OS
account, terminal, or state database. Never let a host automate the console input
or edit approval records; the instruction packs prohibit this. Stronger policies
can require Mode A with `AGENT_APPLY_MINIMUM_ASSURANCE=MODE_A`.

Mode A trusts only an active Ed25519 public key in
`AGENT_TRUST_ROOT/<project-id>.json` (default `~/.agent-platform/trust`) bound to
the Git root commit. Bootstrap this public TrustRecord through a trusted operator
process; repository keys cannot authorize themselves. The CLI accepts
`--trust-root` and `--key-fingerprint` and requests `ssh-keygen -Y sign -U` using
the public key. Private key bytes are never loaded by the server. Keep the signer
under human control, preferably with explicit confirmation for every signature.
A shared unconstrained SSH agent is not evidence of human intent. Actual host
human assertions are not implemented or claimed until a verified host hook exists.

Approval records bind the exact ChangeSet, validation execution, policy, source
base, actor, assurance, expiry (15 minutes), and single-use nonce. They live in
external SQLite and `state/runs/<run>/approvals/`, leaving source Git clean.
Repaired bytes require restaging, validation, and fresh approval. Expired approvals
can be reviewed again. Source drift requires a new plan.

## Recovery and handoffs

Retain project/plan/step/ChangeSet/operation IDs and the state/staging roots.
Request IDs are scoped to the project; reuse with different payloads is rejected.
Status includes clean Git state, bounded diagnostics, and a polling delay.
Cancellation is cooperative for staging/validation; apply cannot be interrupted
after its write intent.

On restart, the server reconciles `APPLY_INTENT` against saved backups and expected
targets under an exclusive apply lock. Uncertainty becomes `RECOVERY_REQUIRED`
and never automatically replays source writes. Inspect the recorded backup,
manually restore the complete base if necessary, then use:

```text
agent recover <step-id> --project-root <source> --plan <plan-id> --state-dir <state> --staging-root <staging>
```

Recovery verifies the restored base or completed target. A recovered base
invalidates the old plan; partial/unknown state remains blocked. There is no GUI
dependency in this workflow.
