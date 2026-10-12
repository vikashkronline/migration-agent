# RBAC review findings — disposition and hardening

Date: 2026-10-10  
Scope: The supplied post-implementation RBAC review; bounded access-proof and recovery hardening, regression coverage and operational clarification.  
Status: Bounded hardening verified; all required repository and UI regression gates passed.

## Outcome

Two reported inconsistencies were fixed: production access-policy verification now accepts only purpose-bound OpenSSH signature envelopes, and recovery reads the external anchor through the same bounded inspection path as other access records. Genuine OpenSSH tests additionally exposed and fixed a Windows execution-environment defect that the earlier raw-signature fixtures did not exercise.

No source application or migrated target code was edited. No real owner/key enrollment, role change, remote provider operation, upstream Git permission change or migration apply was performed. Test keys are ephemeral and remain in memory.

## Finding disposition

| Supplied finding | Disposition | Reason and evidence |
| --- | --- | --- |
| Raw `ed25519-base64:` accepted by access verifier | Fixed: removed production fallback | Access and enrollment proofs require an armored OpenSSH envelope verified by the installed trusted `ssh-keygen` in `migration-agent-access-v2`. No production environment switch was added. Tests use genuine envelopes rather than a bypass. |
| Recovery anchor read bypasses 2 MB budget | Fixed | `recover()` now uses `_read_text(self.trust, self.anchor_name)`, retaining path confinement, bounded inspection and `ACCESS_CORRUPT` rejection. Oversized state preserves the intent and current pointer; valid restored state can subsequently recover. |
| Operational Windows token errors do not use `whoami` fallback | Intentional fail-closed behavior retained; documentation clarified | An impersonated or uninspectable thread must not silently become the process/subprocess account. Only missing API bindings trigger the guarded fallback; token failures remain terminal. |
| Signed HTTP activation increases loopback surface | Transport retained and clarified | The endpoint accepts externally obtained exact signed revisions; it cannot create owner signatures. The GUI still only prepares proposals and displays the terminal handoff. Session/Origin/CSRF, current authorization, saved-proposal comparison, signatures, expiry and replay gates remain enforced. Adding an optional daemon activation mode would create configuration surface without correcting an observed bypass. |
| Synchronous Git directory lookup | Existing request-thread behavior verified; limitation documented | `ThreadingHTTPServer` serves unrelated requests concurrently. A regression holds a directory request open while successfully reading the session. Fetching remains synchronous per request; no async worker/cache, cancellation or automatic retry was introduced. |
| Missing Linux container machine ID | Prerequisite retained and documented | Managed-host identity requires a stable lowercase 32-hex machine ID plus effective UID. Missing/malformed IDs fail closed. Tests cover absent, malformed and valid identity inputs. |
| Upstream Git permission drift | Explicit administration boundary documented | Git directory roles are informational; upstream removal does not revoke agent permissions. Owners must activate signed removal/suspension during offboarding. No webhook/polling infrastructure was added. |
| Approval lifetime sensitive to clock skew | Exact lifetime preserved; boundary tests and guidance added | Activation rejects a host clock before creation and at/after expiry. Keep clocks synchronized and prepare fresh proposals; no grace window or lifetime downgrade was added. |

The original raw access proof was cryptographically verified over a purpose-bound digest. It was not equivalent to the contained legacy public-key HMAC flaw. Removing it enforces a narrower format contract and ensures access tests exercise the deployed OpenSSH path.

## Additional defect found during verification

On the exercised Windows host, OpenSSH 9.5 exited with code 255 and no diagnostic when called with the previous sanitized environment. The same valid test envelope verified successfully with `PROGRAMDATA` available. Isolated environment checks established that adding this non-secret OS directory was sufficient; inheriting the full environment was unnecessary.

`AccessSignatures._env()` now supplies the common application data directory through standard-library `ctypes` and Windows `SHGetFolderPathW(CSIDL_COMMON_APPDATA)`. It does not trust an inherited `PROGRAMDATA` override. Signing and verification share this environment. The executable continues to come from the OS system directory. The regression suite verifies both real envelope validation and the environment allowlist.

The test-only envelope helper follows the primary [OpenSSH signature format specification](https://raw.githubusercontent.com/openssh/openssh-portable/master/PROTOCOL.sshsig). It signs the namespace-bound envelope with an ephemeral in-memory Ed25519 key; the production verifier checks that envelope using OpenSSH. No private key file, external account or provider credential is needed.

## Changed surfaces

- [Access signature adapter](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/access_signatures.py>): reject raw access proofs; include trusted Windows common application data in the sanitized signing/verifying environment.
- [Access storage](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/access_store.py>): bounded recovery anchor read.
- [OS adapter](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/os_identity.py>): standard-library resolution of the trusted Windows common application data directory. Identity failure/fallback semantics are unchanged.
- [Signature fixture](<C:/Projects/New folder/migration-agent/tests/unit/ssh_signature_fixture.py>) and existing access fixtures: produce genuine OpenSSH access proofs without persisting private keys.
- [Signature tests](<C:/Projects/New folder/migration-agent/tests/unit/test_access_signatures.py>), [identity tests](<C:/Projects/New folder/migration-agent/tests/unit/test_os_identity.py>), access/recovery/HTTP tests: format, namespace, key/message binding, bounded recovery, clock interval, identity fail-closed behavior and HTTP concurrency.
- [User operations](<C:/Projects/New folder/migration-agent/docs/rbac-and-users.md>): proof format, compatibility, activation transport and deployment boundaries.

## Compatibility and residual limits

The strict format applies to access-policy and enrollment verification. Workflow apply/native-consent proof formats are separate contracts; this slice does not remove the raw format from `LocalApprovalProof` or claim universal OpenSSH-only verification across every platform proof type.

External integrations producing raw access proofs must change before upgrading. Existing raw-signed historical revisions cannot pass the strict full-chain recovery/publication verifier. No automatic history rewrite, anchor deletion or rebootstrap is provided. A previously deployed raw-proof history needs an independently reviewed migration; this workspace's prior acceptance did not enroll a real owner.

Directory timeout bounds are per subprocess, not per whole request. One metadata request plus up to eleven member pages, each with a 20-second limit, can approach four minutes. The GUI times out after 15 seconds and does not cancel the server's read-only request. Concurrent responsiveness does not eliminate that UX limitation or provide high-concurrency resource guarantees. A total deadline/background flow needs a separately specified slice.

The HTTP route is a signed-proof submission transport, not an independent human signing channel. For physical presence assurance, keep the signing agent/hardware confirmation requirement; an attacker controlling the trusted OS account is outside the current trust boundary. No remote publication protection or provider offboarding automation was established by these tests.

Linux identity branches are exercised with deterministic fixtures on Windows. This does not claim live Linux/container acceptance or modify machine IDs. Clock tests preserve the exact signed interval and do not certify cross-host trust relocation.

## Verification ledger

| Required gate | Result |
| --- | --- |
| `uv sync --all-groups` | Passed; 69 packages resolved, 68 checked |
| `uv run pytest` | **717 passed, 3 skipped in 765.71s**; log `reports/rbac-hardening-20261010/pytest.log` |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 323 files |
| `uv run mypy src` | Passed; 146 source files |
| `uv run migration-agent doctor` | Exit 0 / status `ok`; execution/backend and browser prerequisites remain explicit |
| `npm run test` | Passed; 24 tests in 10 files |

Focused genuine OpenSSH/access/HTTP/integration checks passed after fixing the Windows environment. The new identity and concurrent-directory checks also passed. Initial failed runs exposed the sanitized-environment defect; they are not advertised as successful acceptance.

No GUI implementation or bundled UI assets changed. The full offline suite includes
the amended access fixtures and 16 additional regression cases. All required gates
passed on Windows/Python 3.12.14. Only documentation was updated after that run;
no later phase, compatibility migration or background directory infrastructure
was implemented.
