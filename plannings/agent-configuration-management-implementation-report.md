# Configuration management implementation report

Date: 2026-10-12. Scope: the user-authorized configuration-management implementation following
`agent-configuration-management-plan.md`. Platform implementation only; no selected Ember source
or migrated target application was manually edited.

## Delivered

| Milestone | Implementation |
| --- | --- |
| C0/C1 | Typed, strict public contracts; supported-field registry; constrained resolver with provenance; explicit capability adoption; minimal session bootstrap; CLI/API inspection |
| C2 | Control Center Settings sections; personal choices; separate local/shared drafts; permission gating; field feedback; stale/disconnected/unknown-outcome handling; unsaved-navigation confirmation |
| C3 | Immutable shared candidates; atomic proposal/receipt publication; exact owner terminal handoff; signed protected-file activation and recovery; typed setup and root-restart arguments; history/restore |
| C4 | Durable bounded offline/provider/tool checks; pinned runtime and worker snapshots; SDK endpoint/disclosure restrictions; audit provenance; architecture constraints; foundation workflow hardening |
| C5 | Focused security/recovery/runtime tests; GUI tests; real production-client browser checks; packaged static assets; user and operator documentation |

Main code boundaries: `domain/configuration.py`, `application/configuration.py`,
`ports/configuration.py`, `adapters/configuration_*.py` and
`ui/control-center/src/app/workbench/settings/`. Signed file activation extends the existing access
store rather than adding an unsigned authority pointer. Durable drafts/receipts/checks reuse the
existing operational database. Local preferences stay outside source, governance, state, staging
and trust and are scoped to the verified project and principal.

## Important fixes found during implementation

- Saving a local choice previously risked discarding unrelated shared edits; scope tracking now retains them.
- Unknown responses now replay the exact original request and check kind.
- Proposal and receipt publication is transactional. Local-save and activation receipt interruptions
  recover from the exact persisted envelope or verified signed revision.
- Runtime consumers apply actual approved choices rather than merely displaying them. Public JSON
  escaping cannot disable typed configuration enforcement. Launcher overrides cannot expand authority.
- Provider destinations are pinned; source analysis, planning, contextual answers, connectivity and
  browser review have separate approved data purposes.
- Existing signed role grants remain unchanged until explicit owner adoption.
- Knowledge inspection no longer creates directories during reads.
- The Foundation Wizard's permissive fallback, shared session/CSRF shortcut, fabricated approval,
  fake policy/evidence and file-presence readiness were removed. Grounded plan staging, truthful
  mapping DTOs, explicit mapping decisions and current artifact validation replace them.
- Shared architecture re-confirmation binds the actual draft digest, including mapping changes.
- Existing access API error semantics are preserved; malformed configuration models receive a
  configuration-specific invalid-request response without echoing rejected input.

## Verification

Verified gates:

| Command/check | Result |
| --- | --- |
| `uv sync --all-groups` | Resolved 69 packages; checked 68 installed packages |
| Full `uv run pytest` run | 773 passed, 3 platform-specific skips, 892.84 seconds |
| Follow-up foundation/host/configuration verification | 19 passed; includes mandatory validation before dependent functional staging and optional personal profile selection |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | 349 files formatted |
| `uv run mypy src` | Passed, 160 source files |
| `uv run migration-agent doctor` | Status `ok`; all checks passed; no repository code executed |
| UI lint and format checks | Passed |
| UI unit tests | 37 passed, 13 files |
| Production UI build | Passed; emitted packaged assets into `src/migration_agent/ui/static` |
| Final production Settings browser acceptance | Passed against genuine signed loopback governance |

An earlier full run exposed an access endpoint status-code compatibility regression. The
regression was corrected and the successful full run above supersedes that result. No live
provider call or real-owner approval was required for offline verification.

GUI unit tests: 37 passed in 13 files. Production build succeeds; existing Mermaid CommonJS
optimization warnings remain non-fatal. Real loopback browser acceptance checks personal model
saving, shared proposals, exact owner handoffs, responsive layout and dark mode with no external
requests. Screenshots are in `reports/configuration-verification/`. Source fixture bytes remain
unchanged, and the browser does not activate the shared proposal.

The foundation acceptance test submits grounded analysis and a plan through the host service,
stages via the Control API, verifies ten agent-generated files, retains an unsigned plan, and
confirms that staging alone does not set readiness. A dependent functional step is rejected
with `FOUNDATION_VALIDATION_REQUIRED` before generation until its foundation is validated.

## Deliberate product boundaries

- Final target directories are planning only; destination-aware publication is unavailable.
- Source/governance identities cannot be hot-edited. New-source setup returns reviewed terminal
  arguments; no unbound repository is opened or modified by the configuration API.
- Root handoffs preserve old history/artifacts; they do not copy, move or delete operational state.
- Unknown legacy workflows are preserved and blocked rather than silently rewritten.
- No credential vault/OAuth flow, arbitrary provider endpoint, automatic installation, remote daemon,
  Git membership polling, raw GUI JSON editor or automatic server restart was introduced.
- Provider/installed-tool probes are opt-in and configuration checks do not replace real build,
  test, browser or execution-consent gates.

See `docs/project-configuration.md` for use, permissions, adoption and recovery.
