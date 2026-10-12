# Project users and signed governance

The agent resolves project permissions from an owner-approved access revision.
Git collaborator roles are displayed as context; they do not grant agent roles.
CLI `--actor` labels, browser session tokens, MCP launcher capability settings and
project-work ownership declarations cannot elevate a principal.

Governance, source, state, staging and external trust must have separate roots.
Selected migration sources remain read-only. The governance repository holds
public signed access history; operational proposals live in state. External trust
pins the binding, verified active manifest, revision floor and consumed nonces.

## Owner bootstrap

Use committed source and governance Git repositories and an existing OpenSSH
Ed25519 **public** `.pub` file. The private key remains in the user's SSH agent.
On Windows the platform uses the OS token SID. Linux uses a host-scoped machine
identity plus effective UID. Git usernames and display names are not identities.

```powershell
agent access identity
agent access capabilities
agent access bootstrap 'C:\Work\governance' `
  --source 'C:\Work\source' --id migration-project `
  --owner-key 'C:\Users\Owner\.ssh\owner.pub' `
  --state-dir 'C:\Work\state' --trust-root 'C:\Work\trust'
```

Bootstrap prepares a public proposal; it does not activate an owner. Review the
returned proposal ID and exact policy:

```powershell
agent access review 'C:\Work\source' PROPOSAL_ID `
  --state-dir 'C:\Work\state' --trust-root 'C:\Work\trust'
agent access approve 'C:\Work\source' PROPOSAL_ID `
  --state-dir 'C:\Work\state' --trust-root 'C:\Work\trust'
```

The approval command requires an interactive terminal, the complete exact digest
confirmation, and a genuine owner-key signature. It cannot accept a local session
token as an access-change signature. For high assurance, configure the external
signing agent/key to require human confirmation or hardware presence. A TTY alone
does not establish physical presence against an attacker controlling that OS user.

Access-policy and enrollment proofs require an armored OpenSSH `SSHSIG` envelope
verified in the `migration-agent-access-v2` namespace. Raw `ed25519-base64:` proofs
are rejected; no environment variable enables them in production. OpenSSH signing
and verification on Windows receive the OS-resolved common application data
directory (`PROGRAMDATA`) rather than an inherited override. Offline RBAC fixtures
use ephemeral in-memory test keys to produce genuine envelopes; they never enable
a production verification bypass. This access-proof contract is distinct from
the workflow apply/native-consent proof formats.

If an external integration previously supplied raw access proofs, replace that
integration before upgrading. Historical raw-signed revisions cannot pass strict
history recovery/publication verification. Preserve external trust and arrange
an explicitly reviewed migration of that deployment; do not edit signed history,
delete anchors or silently bootstrap a replacement authority.

Use the same trust and state settings when launching other commands. Set the
public `AGENT_TRUST_ROOT`, `AGENT_STATE_DIR` and `AGENT_STAGING_ROOT` paths or supply
the corresponding command options. Operational migration project IDs and the
logical governance security ID are distinct; the binding preserves both scopes.

## Built-in roles

Roles are finite capability sets, not special names. Owners must additionally be
listed as owners, have an active non-expiring OS identity and enrolled signing key,
and retain access administration permissions. Custom roles are supported.

| Default role | Intended permissions |
| --- | --- |
| Owner | Registered project capabilities, including signed access/rule administration |
| Developer | Read, submit analysis/plans/repairs, stage, validate and request review |
| Reviewer | Read, request review, sign workflow approval and approve knowledge |
| Operator | Developer permissions plus apply and native execution consent |
| Viewer | Inspection and public access read models |

Effective grants are the union of assigned active roles, intersected with the
trusted client ceiling. Expired, suspended, pending and unknown members receive
no effective grants. Agent/MCP clients cannot sign human approvals, activate
access/rules, authorize native execution or approve curated knowledge.

`agent access show`, `status`, `explain` and `capabilities` expose the policy,
current identity, permissions and supported catalog. Uninitialized projects allow
limited inspection; governed writes require owner bootstrap. Unsupported or
corrupt initialized access state never falls back to permissive legacy settings.

## Existing Git users

In **Users and access**, expand **Governance Git connection**, select GitHub or
GitLab, enter its host and `organization/repository`, and discover the stable
repository ID. Prepare and inspect the connection proposal, then use its complete
trusted-terminal handoff. Refresh after activation.

The connection itself is owner-signed. Member requests must match its provider,
host, repository and stable provider repository ID. An altered directory request
cannot substitute a different repository.

Load Git members, select existing accounts, and select explicit agent roles.
Review the before/after policy and confirm the signed proposal in the terminal.
New imports are **pending**. The agent does not create Git accounts, invite users,
change Git permissions or infer ownership from maintainer/admin/reviewer labels.

The read-only adapters use installed authenticated `gh`/`glab` clients with fixed
GET arguments, bounded pages/timeouts and sanitized output. The agent never asks
for, reads or stores their credentials. Missing clients, denied directory access,
incomplete pages and changed repository identity are explicit failures. The
directory includes effective membership where the provider exposes it:
[GitHub collaborators](https://docs.github.com/en/rest/collaborators/collaborators),
[GitLab effective members](https://docs.gitlab.com/api/project_members/).

CLI equivalents include:

```text
agent access repository-propose SOURCE --provider github --host github.com --repository org/governance --repository-id 123
agent access git-members SOURCE --provider github --host github.com --repository org/governance
agent access git-import SOURCE --provider github --host github.com --repository org/governance --account-id 42 --role reviewer
```

Each governance mutation produces a proposal. Supply the configured state/trust
options to these commands as needed. No implicit Git-role synchronization or
provider OAuth sign-in is implemented: owners manage agent membership separately.

Removing a person from GitHub/GitLab does not automatically suspend their agent
membership. There is no revocation webhook or polling service. The owner must
review current Git membership and activate a signed agent suspension/removal as
part of offboarding; expiry can bound delegated membership where appropriate.

Directory requests run synchronously in their individual HTTP request thread.
The server is threaded, so a slow directory request does not serialize unrelated
requests. Each provider call has a 20-second timeout, with one metadata request and
up to eleven member-page requests: the aggregate can approach four minutes.
The GUI's 15-second response timeout may therefore expire while the read-only
request continues; it does not cancel the provider process. No partial result is
accepted as complete. Background fetching, a total deadline and rate-limit-aware
retry are not implemented or implied by the current timeout/page bounds.

## Enrollment, suspension and ownership

Ask a user to run `agent access identity` in the managed OS context. The owner
proposes the intended stable OS binding with `access member-set`, preserving the
imported Git account. A local OS identity can support Mode B ordinary workflows.
For cryptographic review or ownership, enroll that user's public key too.

New public keys must sign the same exact candidate proposal to prove possession.
The user runs `access enroll-sign SOURCE PROPOSAL_ID --public-key USER.pub
--output STATE/proof.json`. Proof output must remain in state. The owner supplies
the public proof through `access approve --enrollment-proof STATE/proof.json`.
Only public keys/proofs are handled by the platform.

Use the GUI member editor or `access member-set --status suspended` to revoke
effective rights, `member-remove` for removal, and `role-set`/`role-remove` for
finite custom roles. Membership expiry is evaluated on every authorization.
Previously issued approvals/consents bind their principal and access digest;
policy changes invalidate them, and signer eligibility is checked again.

`access owners-set --owner PRINCIPAL` prepares ownership changes. Every incoming
owner must consent with its enrolled key, including users already enrolled for
another role. The last eligible owner cannot be deleted, suspended, expired or
stripped of access administration. Key rotation requires both current authority
and possession of the replacement key. Signed revisions retain the prior policy
and public proof history after removals.

This is a local managed-host identity model. Trust roots and their write permissions
must be administered outside an untrusted checkout. A user controlling the trusted
OS account, trust files or installed verifier is outside this enforcement boundary.
Clones/relocations are not silently rebound; changed roots or repository identity
fail closed. Share or provision trust only through an independently trusted process.

The Windows `whoami /user /fo csv /nh` fallback is only for unavailable token API
bindings (`AttributeError`/`NotImplementedError`), and still requires resolution
of the trusted system executable. Token inspection, impersonation and other
security configuration failures remain terminal; falling back in those cases
could substitute a different security context.

Linux requires a valid lowercase 32-hex machine ID at `/etc/machine-id` or
`/var/lib/dbus/machine-id`. Minimal containers/CI runners must provision a stable,
appropriately isolated machine identity through their trusted host administration.
Do not clone the same machine-ID/UID pair into unrelated principals or generate a
fresh ID on every start of a persisted trust deployment. Missing/malformed IDs
fail closed; usernames and random fallback identities are not accepted.

Access proposals use the activation host's wall clock with the exact interval
`created_at <= now < expires_at`, at most 15 minutes. Keep clocks synchronized
when exchanging proposals/proofs, and review/sign promptly. A clock before
creation or at/after expiry rejects activation. Synchronize time and prepare a
fresh proposal if needed; do not edit signed timestamps or widen the lifetime to
work around skew. Relocated roots still require independently trusted rebinding.

## Rules, recovery and concurrency

Execution reads the signed governance policy. Policy/config/rule/workflow files
must match their owner-approved digests. JSON is compared canonically; text rule
line endings are normalized, so CRLF conversion does not create false changes.
Duplicate configuration keys are rejected.

After an intentional governance rule edit, `access rules-propose SOURCE` captures
its bounded public digests. Workflow execution stays blocked until the owner
reviews and signs the new revision. Security changes always require Mode A.

Activation uses an access coordination fence. Source apply obtains that fence
before its project apply lock and holds it to a complete apply/rollback checkpoint.
Validation does not hold the access fence; revocation can activate while validation
runs, and worker heartbeats stop work at the next safe boundary. Policy reads
verify the active manifest against the external trusted head without acquiring
the writer fence. Busy fences report a retryable conflict, not an indefinite wait.

An interrupted activation leaves an external durable intent and fails closed.
`access recover SOURCE` verifies that intent and signed history before finishing
the pointer transition. It cannot invent a new authority or unsigned policy.
Revision locators use collision-checked 16/24/32 hex prefixes; full SHA-256 values
remain in the manifest and pointers. Windows path budgets fail with a shorter-root
prerequisite before writes.

## Governance Git enforcement

Agent RBAC rejects unsigned effective access and rule changes. Blocking raw Git
pushes also requires remote Git controls. Protect the authoritative governance
branch, block force pushes, restrict bypass, and require the verifier from a trusted
installation/runner whose code and trust are outside the proposed commit.

```text
agent access verify-publication SOURCE --commit EXACT_COMMIT_ID --state-dir STATE --trust-root TRUST
agent access gate-status SOURCE --state-dir STATE --trust-root TRUST
```

The publication verifier reads immutable Git objects, validates the signed chain
against the external trusted revision, rejects rollback, and verifies rule content.
It never executes candidate repository code. A pre-receive hook can reject a push;
a trusted required check can reject promotion/merge into the authoritative branch.
Feature-branch pushes are not prevented by an ordinary required PR check alone.

Do not run the candidate commit's verifier or let that commit supply its own trust
baseline. Verify an actual rejected unauthorized push on the chosen server.
`gate-status` deliberately reports `REMOTE_ENFORCEMENT_UNVERIFIED` until that
external configuration is established. No live Git server protections were changed
by this implementation.

## Verification and release status

Focused offline tests cover genuine signatures, fake actor labels, pending Git
imports, repository substitution, role/owner constraints, rollback, current worker
rights, exact HTTP activation and CSRF. Existing workflow mechanics tests use
explicit opt-in test authorization; production composition has no permissive test
switch. Browser acceptance uses disposable repositories and ephemeral test keys.

The implementation report records the final full-suite, UI, package and source
integrity gates. Actual owner/key enrollment and real provider/server acceptance
remain deployment prerequisites; tests do not simulate them as completed setup.
