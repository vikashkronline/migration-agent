# Browser UI/UX implementation report

Date: 2026-10-05. Scope: the explicitly requested browser validation amendment.
Status: host/CLI workflow and explicitly authorized opt-in OpenAI/Gemini visual
provider adapter implemented. Live acceptance remains pending.

## Delivered

- Typed versioned rules, route/state/viewport coverage, browser manifests, captured
  images, findings, review and optional final journey results.
- Fixed Playwright Core worker serving the composed staged build on loopback,
  with actual screenshots, DOM geometry, accessibility names/ARIA snapshots and
  keyboard evidence. No raw model JavaScript or shell execution.
- Mandatory lint/typecheck/test/build before browser review; version 3 immutable
  execution evidence checked by the shared human review/apply path.
- Supervised native capture with active consent, fixed tool identities, positive
  environments and checked cleanup. Windows Chromium runs with fresh browser
  profiles while receiving required non-secret Windows known-folder metadata.
- Fixed container worker with read-only source/staging/worker mounts, one fresh
  writable capture mount, network denial, fixed image/tool identity and cleanup.
- Capture batching and total time/size limits; complete required coverage and exact
  image hashes/dimensions required. No pass for missing, uncertain or stale evidence.
- Three typed MCP tools and CLI browser-request/browser-submit commands for AI
  specialist review. Host model responses remain untrusted, scope-checked input.
- Repair proposals cite current browser diagnostics, create new ChangeSets, restage,
  recapture and require new review. Repair count is durable across resumes.
- Optional paired source screenshots with distinct legacy selectors/routes and
  read-only source-runtime navigation. Optional E2E runs last and blocks on failure
  when enabled; disabled tests remain explicitly not run.
- Original version 1/2 serialization/hash compatibility preserved for historical
  records. Such records cannot authorize new browser-gated apply.

## Measured results so far

- Existing shared workflow/MCP regression run: 38 passed.
- Browser core run after initial fixture correction: 29 passed, one measured-browser
  case deselected. Further profile/renewal/container/history regressions were added.
- Actual offline Windows Chromium initially failed because the fully fresh account
  environment broke Chrome known-folder discovery. After the scoped environment
  correction it produced real viewport screenshots and detected injected mobile
  overflow: one passed in 23.89s; a subsequent full-page/ARIA capture run passed
  in 37.23s. These are browser implementation measurements, not live AI acceptance.
- Windows type checking passed for 114 source files before the final gates.

Final combined gates on 2026-10-05:

| Gate | Result |
|---|---|
| `uv sync --all-groups` | Passed; 69 resolved, 68 checked |
| `uv run pytest` | **526 passed, 2 skipped in 523.89s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 237 files |
| `uv run mypy src` | Passed; 114 source files |
| `uv run migration-agent doctor` | Exit 0; status `ok` |
| `uv run agent doctor` | Exit 0; status `ok` |

The full run used test-only paths for the already installed Playwright Core and
Chromium, so the actual-browser case ran instead of being skipped. No provider
key or network is required by the tests. Linux-targeted type checking and
`git diff --check` also passed. The final focused run passed 72 tests; 35 browser
cases are included in that baseline suite. The authorized provider completion and
new gate results are recorded below; repository gates do not replace live acceptance.

## Authorized provider completion

Automatic approval review rejected the patch adding direct OpenAI/Gemini provider
calls, because it would export screenshots, page metadata and editable staged files
without explicit authorization for those external destinations. That patch was not
applied. The user subsequently explicitly authorized completing that opt-in adapter.

The adapter now sends verified PNGs and bounded per-case metadata/editable staged
code only when trusted launcher export is explicitly enabled. Provider, configured
model, fixed endpoint and limits are bound into execution policy/native consent.
SDK errors are sanitized; incomplete/refused/invalid reviews and conflicting repairs
fail closed. Disclosure drift invalidates capture reuse, and active native consent
is checked before/after provider calls. Complete reviews enter the same deterministic
scope/repair gates; automatic repair creates a new artifact and recaptures, with
optional E2E last and separate exact human source approval.

Offline tests cover both real SDK request shapes with mocked transports, optional
paired source images, opt-in/preflight rejection, malformed output, stale references,
conflicts/scope, revocation, cached-review invalidation and the complete autonomous
visual repair/recapture/E2E/human-apply journey. No API keys or live calls are used.

### Authorized adapter quality gates — 2026-10-05

| Gate | Result |
|---|---|
| `uv sync --all-groups` | Passed; 69 packages resolved, 68 checked |
| `uv run pytest` | **558 passed, 2 skipped in 642.94s** |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 239 files |
| `uv run mypy src` | Passed; 115 source files |
| `uv run migration-agent doctor` | Exit 0; status `ok` |
| `uv run agent doctor` | Exit 0; status `ok` |

The full suite included actual Windows Chromium capture using test-only installed
runtime paths. Final provider/MCP setup checks passed **37 tests, one deselected**;
the separate real native disclosure/consent binding and revocation test passed.
Linux-targeted mypy passed for 115 source files, and `git diff --check` passed.
The new provider module contributes 32 offline tests to the combined suite.
Provider SDK credentials, external API calls and selected source mutations are
absent from implementation tests; the final apply journey uses a disposable fixture.

## Remaining measured acceptance

Actual Antigravity/Codex specialist journeys, configured standalone vision, real
Angular application integration, real Docker and Linux browser execution remain
measured acceptance work. Chromium viewport/zoom emulation is not physical-device
coverage or full WCAG certification. Source screenshots cannot establish complete
functional parity. Backend fixtures must be separately provisioned, authorized
loopback test services; the agent does not silently launch them or mutate source.

See [operation guide](../docs/browser-ui-ux-validation.md).
