# MCP host compatibility and human approval evidence

Updated: 2026-10-04.

## Verification status

The Phase 16A server exposes five inspection tools over stdio. Automated tests exercise the installed Python MCP SDK client and a subprocess JSON-RPC client. They verify initialization, schemas, normal tool calls, source isolation, result protection, read permissions, startup failure, and stdin EOF.

**Actual Antigravity and Codex host sessions have not been verified by this evidence.** The previous version asserted host protocol revisions and human-input limitations without measurements. Those assertions have been withdrawn. A chat prompt or tool confirmation UI does not, by itself, establish an authenticated human assertion to this server.

| Target | Version/build recorded | Inspection session measured | Human assertion channel measured | Classification |
|---|---|---|---|---|
| Antigravity | Not recorded | Pending | Pending | Required primary target; unverified |
| Codex desktop/CLI | Not recorded | Pending | Pending | Required primary target; unverified |
| Installed Python MCP SDK | 2.2.0 | Automated contract coverage | Not a human approval channel | Verified test client |
| Subprocess JSON-RPC client | Repository contract fixture | Automated CLI stdio coverage | Not a human approval channel | Verified test client |

SDK tests cover the revisions in the accepted plan: `2024-11-05`, `2025-03-26`, and `2026-07-28`. This does not assign these revisions to any particular IDE.

## Current inspection boundary

The launcher binds one canonical source root and mints a root-derived project ID. A manifest ID is a validated declaration, not an authority or a means of selecting another source. Stored plans/runs must belong to that same root. Operational state and configured staging roots must be separate from source and each other.

The local stdio launcher resolves an OS account and creates an immutable inspection context. A trusted single-user launch grants **Mode B inspection only** by default. `AGENT_MCP_TRUSTED_LOCAL_READS=false` lowers it to Mode C. `AGENT_MCP_READ_CAPABILITIES` is an optional JSON array controlled by the local launcher that can narrow inspection capabilities. Neither is a tool argument or human approval proof.

| Tool | Capability | Minimum assurance |
|---|---|---|
| `migration_doctor` | `system.diagnostics` | Mode C |
| `migration_inventory` | `project.read` | Mode C |
| `migration_run_status` | `run.read` | Mode B |
| `migration_plan_show` | `plan.read` | Mode B |
| `migration_step_preview` | `changeset.read` | Mode B |

There are no mutation or approval tools in 16A. Preview may save ordinary ChangeSet state outside source; it cannot stage, sign, approve, or apply. Local read grants are not the future authority policy for apply.

## Accepted human approval design for 16C

The final plan requires a distinct **`ApplyApprovalRecord`**, bound to the exact ChangeSet, project/run/step, base, validation provenance, policy, and trusted actor. It is stored in SQLite and an out-of-source operational run directory. Creating it must not dirty source or change the approved base fingerprint.

A legacy plan `ApprovalSignature` is not the required authorization for final ChangeSet apply. The future `agent review` / step approval flow belongs to 16C and is not provided by the current MCP implementation. Approval records must not be exported into `.agent/plans/` during pre-apply review.

Terminal-assisted human review is the conservative fallback in the accepted plan. In-IDE approval is allowed only after a measured host channel supplies a human assertion the server can authenticate and the model cannot manufacture. A model-callable signer, actor string, reusable bearer secret passed in arguments, or automatic yes flag is insufficient.

Relevant master-plan invariants are 5–7 (exact approval, validation, policy), 9 (state separation), 14 (sensitive data), and 24 (out-of-band authority trust). Invariant 10 defines the GUI as a Control API client; it is not the human approval invariant.

## Required host spike procedure

Execute independently in Antigravity and Codex, retaining dated observations:

1. Record exact product, version/build, OS, launch configuration, and negotiated protocol. Use disposable source and separate state.
2. Launch `agent mcp serve --project-root <source> --state-dir <outside-state>` through that client. Record initialization and the exact five-tool list.
3. Call doctor, inventory, plan show, run status, and a valid step preview. Obtain the opaque project ID from inventory; do not infer it from the directory name.
4. Exercise a foreign record, unknown step, and credential-shaped synthetic payload. Verify safe failures and no source write or foreign disclosure.
5. Determine whether the host exposes an authenticated human-only assertion to an external MCP server. Record its API, actor binding, replay protection, and whether model calls can simulate it. Without that demonstration, classify approval as terminal-assisted.
6. Save sanitized results, versions, reproduction steps, and limitations. Do not retain credentials or sensitive transcripts.

Because 16A has no approval/apply endpoint, it cannot demonstrate the full journey. The measured host spike remains a 16A acceptance item; full Antigravity/Codex/standalone smoke verification belongs to 16D after 16B–16C.

## Remaining milestones

- **16B:** typed host proposals, bounded evidence reads, durable/idempotent operations, cancellation, lock/lease fencing, lifecycle enforcement, and recovery reconciliation.
- **16C:** exact-ChangeSet headless human approval and shared guarded stage/validate/apply gates.
- **16D:** preview-first setup generation, host skills/instructions, actual primary-client and standalone smoke verification, and documentation synchronization.

The full GUI remains outside Phase 16 scope.

## Current Phase 16 implementation

The five-tool procedure above records the original 16A scope. The implemented
16B–16D server now exposes fifteen tools, including grounded proposals, evidence,
durable operations, stage/validate/apply, and review requests. Use
`phase-16-smoke-checklists.md` for the current full workflow acceptance procedure
and `phase-16-client-setup.md` for launch configuration.

Shared exact-ChangeSet approval and apply services, external trust/state,
preview-first setup, and instruction packs are implemented. No MCP approve or
signer tool exists. Native IDE human assertions remain unverified; a trusted
interactive human terminal is the implemented fallback. Actual Antigravity/Codex
sessions remain pending and are not inferred from automated SDK fixtures.
