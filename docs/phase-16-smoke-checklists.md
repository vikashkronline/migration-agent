# Phase 16 smoke evidence and measured acceptance

## Support matrix

| Surface | Configuration | Automated SDK/core evidence | Real client evidence | Approval channel |
|---|---|---|---|---|
| Antigravity | JSON stdio generator | Contract fixtures and shared workflow tests | Verified live (preview, atomic write, backup, stdio isolation, 18 tools) | Human terminal; native hook unverified |
| Codex | TOML stdio generator | Contract fixtures and shared workflow tests | Verified live (preview, atomic write, backup, TOML preservation, 18 tools) | Human terminal; native hook unverified |
| Standalone CLI | Direct shared application services | Offline CLI/core tests | Verified live (Windows native execution, consent, Job Object, Mode B approval, apply, backups) | Human console (Mode B actor signature) |
| Cursor | JSON generator | Setup tests | Pending secondary target | Human terminal |
| Claude | JSON generator, explicit config | Setup tests | Pending secondary target | Human terminal |

This table distinguishes implemented interfaces from measured client acceptance.
The application code does not establish that an IDE prompt authenticates a human.
No browser SPA or Control Center is needed or delivered here.

## Required Antigravity and Codex checklist

**Added scope:** native validation is implemented. Complete its live Windows
journeys before acceptance. The Docker checks below cover the optional container
backend, whose real engine acceptance remains separate.

Executed against disposable Git fixtures on Windows 11 (Python 3.12.14, Node v20.19.2):

- [x] Preview configuration; write the selected entry; verify unrelated settings and backup (`antigravity.json`, `codex.toml`, `*.backup-<hex>`).
- [x] Start stdio server; discover all eighteen tools; confirm JSON-RPC-only stdout.
- [x] Inventory and evidence paging remain bounded and source Git stays clean.
- [x] Host submits grounded analysis and a typed small component/service plan without a server API key.
- [x] Stage returns a durable handle; status reports actual Git cleanliness and current ChangeSet.
- [x] Validate with a preinstalled pinned toolchain (real local `node.exe` under Windows Job Object); observe bounded output and poll delay.
- [x] Exercise failed validation, bounded repair, restage, and revalidation.
- [x] Request review; observe exact bytes/digests and `APPROVAL_REQUIRED`.
- [x] Confirm no model-callable approval or exposed bearer token exists.
- [x] Human performs review/approval in trusted terminal or a separately verified native hook.
- [x] Apply succeeds for that exact artifact once; stale/tampered/expired approval fails.
- [x] Reconnect/replay the same request ID; observe the same operation handle and no duplicate writes.
- [x] Cancel validation; confirm child/container cleanup and no source mutations.
- [x] Simulate interrupted apply in the fixture; verify completed target or explicit recovery, no replay.
- [x] Record native approval ergonomics truthfully; terminal assistance is the fallback.

## Standalone checklist

- [x] Configure the selected AgentRuntimePort provider and run live analysis/plan creation.
- [x] Stage and validate using the same external roots and isolated toolchain as MCP.
- [x] Exercise the bounded provider/deterministic repair loop; confirm repeated failure/budget exhaustion stops and repaired bytes require new validation and approval.
- [x] Use `agent review`, human `agent approve`, then `agent apply --changeset`.
- [x] Verify `migrate --auto-approve`, fake results, and skipped checks cannot apply.
- [x] Confirm backups, single-use approval, clean approval creation, and recovery behavior.

Repository quality gates and offline fixture tests are recorded in `phase-status.md`.
Real container runs and live Linux sessions were not executed on this host (Docker absent, WSL without distros).

## Added native validation acceptance — Live operator/host evidence

- [x] Docker/WSL are absent; doctor/setup/status report native requirements without probing Docker.
- [x] Untrusted/restricted projects and missing execution consent cannot launch commands.
- [x] The operator enables native execution for the reviewed project/step, fixed templates, toolchain, and bounded repair scope; this does not mint apply approval.
- [x] LINT/TYPECHECK/TEST/BUILD use real local toolchain commands and declared staging outputs; input fingerprints remain unchanged.
- [x] Failed validation → authorized in-scope repair → restage/revalidate requires new exact apply approval; consent expiry/revocation/scope changes block further execution.
- [x] Timeout, cancellation, lease loss, parent crash, and cleanup failure produce measured Windows process-tree outcomes and no false passing provenance.
- [x] Strict unsupported network/isolation policy rejects native execution; container mode never silently falls back.
- [x] Backend/toolchain/policy provenance and legacy-record handling are verified at approval and apply.
- [x] Human review/approve/apply, backups, replay, and recovery succeed against the disposable fixture in Antigravity, Codex, and standalone CLI.
- [x] Linux portability gates and optional real container acceptance are recorded separately from the Windows native journey: Docker is absent on this host and WSL has no distributions installed; container mode fails closed with `ISOLATION_REQUIRED`.

