# User management and RBAC implementation report

Date: 2026-10-09. Scope: the user's authorization of all required R0–R6 user
management/RBAC implementation, including Git-member import and owner GUI.
Status: implementation verified by the consolidated offline/platform/GUI gates.
This report does not claim live deployment or actual human enrollment.

## Implemented surfaces

- Typed finite role/membership model, stable OS identities, default deny, capability
  union/intersection, client ceilings, human-only capabilities and owner invariants.
- Immutable exact proposals and revisions, purpose-bound Ed25519/SSH signatures,
  possession proofs, two-party owner admission and bounded approval lifetime.
- External binding/verified-manifest anchor, consumed nonces, rollback protection,
  short collision-checked locators, atomic writes and interrupted-activation recovery.
- Owner CLI lifecycle; current member/role changes, suspension/removal, ownership,
  key enrollment/rotation, signed rules and trusted publication verification.
- Signed Git connection plus bounded read-only GitHub/GitLab effective directory
  import. Stable provider IDs are used; Git roles never become agent grants.
- Shared proposal/stage/validate/review/apply authorization; durable operation and
  approval principal/access binding; current worker checks and signer eligibility.
- CLI capability coverage, MCP human ceiling and current grants, canonical
  workbench projections/actions/receipts, authenticated Control API administration.
- Angular owner/viewer page, explicit role forms, connection discovery and imports,
  public diff review, complete trusted-terminal handoff, permission refresh and
  removal of the default GUI read-write claim.
- Legacy public-key HMAC verifier containment. Its callers cannot claim Mode A or
  downgrade. Release signing through that disabled compatibility path fails closed.

## Architecture decisions

Effective access changes retain Mode A; local browser tokens prepare proposals but
cannot substitute for signatures. Validation's workflow lease is independent of
access activation. Access coordination precedes the apply lock; verified policy
reads take no writer lock. Active reads pin the exact manifest verified at
activation in external trust; full history is verified for recovery/publication.

The signed snapshot contains a server nonce, giving every exact proposal a unique
immutable location even when the proposed grants are equal. Its full SHA-256 and
selected locator are approval-bound. Rule JSON hashing ignores formatting and
line-ending differences while retaining effective content integrity.

Identity uses Windows TokenUser SID through stdlib ctypes, with guarded fallback,
or Linux machine identity plus effective UID. Windows signing tools are resolved
from the OS system directory rather than a candidate checkout or environment path.
Domain/application models do not depend on adapters/frameworks.

## Verification ledger

| Gate | Evidence |
| --- | --- |
| R0 full containment suite | 670 passed, 3 skipped; `r0-pytest-final.log` |
| Signed core/transport integration | Focused genuine-proof suites passed; subsequent additions included in final gates |
| Native execution and security regressions | 72 passed; `security-and-native.log` |
| Focused CLI/GUI integration repairs | 34 passed; `focused-repairs.log` |
| Expanded access/API/workbench/security checks | 45 passed; `final-focused.log` |
| Enrolled-key workflow approval | Passed with genuine Ed25519 verification and no legacy trust file |
| Dependency sync | 69 resolved / 68 checked |
| Ruff and format | Passed before the consolidated final run |
| Strict mypy | Passed; 146 source files |
| Doctor | Exit 0 / `ok`; execution/browser prerequisites still explicit |
| Final full pytest | **701 passed, 3 skipped in 623.24s**; `final-pytest-verified.log` |
| UI tests/lint/format/build | **24 tests in 10 files**, lint, format and production build passed; existing Mermaid CommonJS warnings remain |
| Real owner browser acceptance | Passed against real API/packaged Angular client, desktop/mobile; proposal prepared without activating test policy |
| Offline wheel | Built; all 75 checked RBAC/current UI members byte-match workspace; `package-integrity.json` |
| Original source integrity | **2269 identical eligible file records**; no paths/hashes/sizes changed; `source-integrity.json` |

Logs live under `reports/rbac-verification/`. Earlier failing runs are retained as
diagnostic history, not advertised as passed gates.

## Deployment boundaries

No real project owner/key was enrolled, no production role/rule proposal was signed,
no Git member invitation/permission was changed, and no remote protection was
installed. Provider authentication and authoritative Git enforcement need actual
owner/server setup. Windows is the exercised host; Linux portability is implemented
but separate live Linux acceptance is not claimed.

The original migration source is read-only and no migrated target application code
was manually authored. The acceptance migration remains separate from these agent
platform changes. See [user operations](../docs/rbac-and-users.md).


## Final verification disposition

The preceding 697-test full run passed. The expanded final run initially found a
stale empty-project expectation: verified owner initialization now has an explicit
INITIALIZED status while task/readiness counts remain zero. That assertion was
corrected, focused checks passed, and the complete rerun passed 701 tests. The
HTTP rejection regression passed 11 tests after bounded body discard prevents
Windows resets from obscuring authentication/CSRF errors.

Browser captures are under `reports/rbac-verification/browser/`. The offline wheel
is `reports/rbac-verification/dist/migration_agent-0.1.0-py3-none-any.whl`, SHA-256
`41df24be26c5a7484bed7f323ccafd42f423d4f8815ebfa4cd3f6dd3fec81c4c`.

No runtime or GUI changes followed the final consolidated run. Documentation
records completion of the authorized implementation and its deployment boundaries.

## Post-implementation review — 2026-10-10

A bounded hardening amendment removes raw access-policy proofs, uses bounded
anchor reads during recovery and corrects the Windows OpenSSH environment.
The [review disposition](rbac-hardening-review-disposition.md) records the supplied
findings, focused regressions, compatibility limits and amendment quality gates.
The verification ledger above remains the historical 2026-10-09 result.
