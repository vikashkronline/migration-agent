# Browser UI/UX validation

The production shared workflow requires lint, typecheck, test and build results,
then real browser capture and AI visual review, before exact human source approval.
Optional E2E runs last. The agent's own GUI is not required.

## Configure the trusted launcher

```powershell
$env:AGENT_BROWSER_VALIDATION_PLAN = 'C:\AgentConfig\application-browser-plan.json'
$env:AGENT_BROWSER_REVIEW_MODE = 'host'
$env:AGENT_NATIVE_BROWSER_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Native mode also requires the external Node toolchain and offline dependencies
described in [native validation](native-validation.md). Provision `playwright-core`
under that toolchain's `node_modules`. The agent does not install/download browsers
or packages. Its fixed worker, automation modules and browser identity are bound to
execution consent. Configure the plan before human `validation authorize`.

For container mode, provision the digest-pinned image with `node` on PATH,
`/opt/agent-tools/node_modules/playwright-core/index.js` and `/usr/bin/chromium`.
The fixed worker and staged workspace mount read-only; only a fresh capture directory
is writable. Network denial, non-root user, resource limits and checked removal remain
in force. Container source/test origins on the host are unsupported and fail closed.
Actual Docker/Linux browser acceptance remains separate from offline contract tests.

Example plan (adjust routes, states, widths and requirements for the actual project):

```json
{
  "schema_version": 1,
  "version": "application-ui-v1",
  "build_root": "dist/application/browser",
  "design_requirements": "Use the approved design tokens; preserve navigation and form controls.",
  "test_data_identity": "synthetic-acceptance-data-v1",
  "viewports": [
    {"id": "mobile", "width": 360, "height": 800},
    {"id": "tablet", "width": 768, "height": 1024},
    {"id": "desktop", "width": 1440, "height": 900}
  ],
  "cases": [{
    "id": "home", "route": "/", "state": "initial",
    "expected": "Navigation, heading and search controls are usable.",
    "ready_selector": "main",
    "assertions": [{"kind": "visible", "selector": "main h1"}],
    "geometry": [{"rule_id": "typography", "kind": "font_size",
                  "selector": "main h1", "minimum": 24, "maximum": 48}]
  }],
  "e2e_enabled": false,
  "max_repairs": 3,
  "max_validation_seconds": 600,
  "full_page": true
}
```

All eight review dimensions are required: spacing, alignment, typography,
responsiveness, accessibility, interactions, states and visible capabilities.
The default instructions can be replaced with project-specific rule text, retaining
these IDs; additional rules are allowed. WCAG checks and screenshot review do not
constitute a complete accessibility certification.

Each case has a named state and fixed selector-based actions/assertions. There is
no arbitrary JavaScript/shell input. Geometry supports gap, left alignment, font size,
contrast and target size. Coverage is bounded to 64 case/viewport cells, captured in
small supervised batches. Zoom is emulated through CSS viewport size and pixel density;
it does not establish physical-device compatibility. Full-page capture is clipped
to the required viewport width, preserving evidence of horizontal overflow.
Oversized pages need bounded scroll-state coverage. Screenshots and DOM/ARIA facts
are stored under external state/artifact roots with hashes and dimensions checked.

## Host-assisted visual review and repair

1. Stage the saved step, obtain human native execution consent when applicable, and
   run shared validation with `--profile ALL`. Partial command checks cannot satisfy
   browser approval. The first complete run captures the UI and waits for AI review.
2. Fetch `migration_browser_review_request`, which contains specialist instructions,
   standards, coverage, editable scope and screenshot references.
3. Read the actual images with `migration_browser_screenshot`. Work as the UI/UX
   specialist, not solely as a code reviewer. Return one verdict/explanation for
   every rule at every case/viewport, citing target and optional source image hashes.
4. Submit `migration_browser_submit_review`. This records evidence, not source
   approval. Missing cases/rules, fabricated references, unsafe data and expanded
   repair scope are rejected. Objective failures cannot be waived by an AI pass.
5. If findings remain, propose minimal full-file replacements with case/rule citations.
   Use existing repair proposal/stage/validate tools, or `agent validation repair`.
   Every accepted repair creates a new ChangeSet, restages and recaptures. Repeat
   image inspection and review; earlier passing reports do not apply to repaired bytes.
6. Once UI review passes, rerun validation. Enabled E2E journeys execute last.
   Only then request exact human source approval and guarded apply.

The same local interfaces are available through:

```text
agent validation browser-request <step> --project-root <source> --plan <plan>
agent validation browser-submit <step> --project-root <source> --plan <plan> --review <review.json>
agent validation repair <step> --project-root <source> --plan <plan> --max-repairs 3
```

Use identical external state/staging/trust roots in every client/command. Repair
budgets are durable across resumes. Repeated failures, exhausted budgets, missing
analysis or uncertain checks stay blocked. Renewed consent requires fresh browser
capture/review. Approvals recheck build, config, images, review, consent and toolchain.
Old version 1/2 records remain readable history; they cannot satisfy the new browser gate.

## Optional source comparison and final E2E

Set `source_url` to an explicit `http://127.0.0.1:<port>` reference runtime and
provide `source_identity`. The operator starts that authorized runtime; the agent
does not build/install/run inside the selected source. Source capture precedes target
capture and permits GET/HEAD only. `source_cases` can map different legacy routes
or selectors using exactly the target case IDs. Images must pair at the same viewports.
An unavailable/unready selected reference cannot be reported as compared.

Without a reference, source visual parity is not assessed. With one, AI compares
visible controls/content/states while honoring `approved_design_changes`. Screenshots
do not prove API, permission, calculation or persistence equivalence. Source runtime
identity is an operator assertion; it is not cryptographic proof of a deployed build.

Set `e2e_enabled: true` and supply `e2e_cases` for final business journeys using
the same typed actions/assertions. Required backend fixtures may be prestarted on
explicit loopback `test_origins`, separately from the read-only source reference.
No external/production origin is permitted. Container network-denied runs cannot
reach host test origins. Failed enabled journeys block approval; disabled journeys
are `NOT_RUN`, never a fabricated pass.

## Opt-in standalone visual providers

The explicitly authorized adapter supports OpenAI Responses and the Gemini Developer
API. Host mode remains the default and uses the IDE's AI capabilities. To opt into
standalone visual analysis, set these **trusted launcher** settings before validation:

```text
AGENT_BROWSER_REVIEW_MODE=provider
AGENT_BROWSER_PROVIDER_EXPORT=true
AGENT_RUNTIME_PROVIDER=openai
AGENT_RUNTIME_MODEL=<configured image-capable model identifier>
```

Use `gemini` for the Gemini provider. No model is selected implicitly. Provision
credentials through the selected SDK's normal secure environment; do not put them
in the browser plan, MCP tools, generated client configuration or reports. The
adapter does not inspect or print credential values. `agent mcp setup` carries only
the non-secret provider/model and export settings into its client configuration.
The opt-in cannot be enabled through model-supplied tool arguments.

Export includes verified target PNGs, selected optional source PNGs, bounded
DOM/ARIA facts and objective findings, the current case and UI rules/design
requirements, and **all editable file texts in the current ChangeSet** (32 KiB
total). It excludes absolute screenshot paths, other cases' images and arbitrary
repository reads. Use synthetic data: text scanning recognizes credential-shaped
content but cannot establish that screenshot pixels or arbitrary prose are free
of sensitive data. Do not configure production personal data for this workflow.

Destinations are fixed to `https://api.openai.com/v1` and
`https://generativelanguage.googleapis.com`; SDK base-URL overrides are not used.
OpenAI requests set `store=false`; provider retention policies still apply.
The execution policy binds destination, provider, model and payload limits. Native
human authorization displays that disclosure; changing it requires renewed native
consent. Revocation, expiry, cancellation and policy drift are checked before and
after each request. Requests already sent cannot be retracted. Container browser
workers retain network denial; the authorized provider call runs in the server.

There is one request per declared case/viewport, at most 64. Each request carries
at most two images (10 MiB raw combined), 128 KiB metadata and 8,192 output tokens,
with a 30-second SDK transport timeout and no retries. The browser plan's overall
time budget also applies at request boundaries. The verified screenshot bundle
remains capped at 64 MiB. Refusal, missing vision capability, malformed/partial
output, fabricated references or conflicting repairs leave validation blocked.
Only complete, scope-checked reviews are persisted; failed requests can be resumed
against the unchanged verified capture. Changing review mode/model/disclosure
invalidates cached visual evidence.

Run shared validation to capture and review, then `agent validation repair` to
execute the bounded repair loop. No `--provider-guidance` flag is needed for visual
repairs. Each accepted repair creates a new ChangeSet, reruns all required commands,
recaptures and reviews again; optional E2E runs after a complete visual pass. Repair
limits remain durable, and exact human source approval is still separate. Unresolved
or uncertain issues at the budget boundary stop the workflow without a pass.

Offline mocked SDK contracts and the complete repair cycle are tested. Live
provider/IDE/real-application/container/Linux acceptance remains pending; no live
provider transfer or API-key test was performed during implementation.

Native browser execution retains local-account filesystem/network permissions.
On Windows, only the trusted browser worker receives real non-secret known-folder
metadata needed by Chrome. Its browser profile/home/temp/cache remain fresh; provider
keys, SSH/startup variables and personal browser sessions are not inherited.
