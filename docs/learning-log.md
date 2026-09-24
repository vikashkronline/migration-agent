# Learning Log

## Phase 0

The project starts with an inward dependency direction: user-facing delivery mechanisms
such as the CLI may depend on domain concepts, while the domain does not know about the
CLI, filesystem, persistence, framework adapters, or an agent SDK. This makes the core
contracts testable without network access and keeps future runtime choices replaceable.

Pydantic models validate data contracts. `pydantic-settings` is kept in the configuration
layer because environment loading is an application boundary rather than a domain concern.
Typer belongs only to the CLI layer. The OpenAI Agents SDK is intentionally deferred until
Phase 2, where it will implement a narrow application-owned port.

The lockfile captures exact transitive versions while `pyproject.toml` gives direct
dependencies compatible upper bounds. This keeps installations reproducible without
turning every future patch upgrade into a source edit. The project selects CPython 3.12 as
its reproducible development baseline while declaring support for Python 3.12 and newer.

The `doctor` command separates required local health from future runtime configuration.
Python and installed runtime packages are genuine local checks; an unset model is only
informational because Phase 0 performs no API call. Its JSON output reports whether a model
is configured but never prints the value or inspects an API key.

## Phase 1

Repository discovery is deterministic because the filesystem adapter, file classifier,
manifest parser, framework evidence rules, ordering, and serializers are ordinary code.
Running the inventory twice against unchanged input produces the same typed result and
report content; no model interpretation is involved.

Ports express what the application needs without choosing how it is done. The inventory
service depends on `FilesystemInspectorPort` and framework adapter contracts. Concrete
filesystem and Ember/Angular behavior lives outside the application and domain layers. The
registry lets the application evaluate adapters without source/target conditionals.

Evidence is stronger than a framework label alone. A fingerprint records the exact
eligible inventory paths and the weighted signals that produced its confidence. Weak
signals below the adapter threshold produce no detection instead of a guess. Invalid
manifests and unsupported repositories remain inspectable through typed issues or an empty
framework list.

Safe discovery deliberately reads less: recognized files only, bounded sizes, UTF-8 text,
no links or reparse points, and no secret-like filenames. Exclusion reporting uses counts
so a report does not become a secondary index of sensitive paths.

## Phase 2

LLM runtime integration must remain an outer infrastructure adapter behind an application-owned
port (`AgentRuntimePort`). The core platform is provider-neutral: Google Gemini is the default
runtime provider via the official `google-genai` SDK, while OpenAI is a supported parallel provider
via the OpenAI Agents SDK. Neither provider SDK may leak types across the domain or application
boundaries.

The model is strictly an untrusted proposer. Mechanical repository discovery remains the deterministic
source of truth. The agent cannot modify source files or execute arbitrary shell commands; its tools
are strictly bounded to reading already-discovered eligible text files and querying the pre-built inventory.
Access to missing, secret, or excluded files is rejected deterministically by tool guardrails.

Hallucinations are contained post-generation. While agent prompt instructions mandate citing concrete
repository-relative POSIX paths and forbid inventing symbols, the application service audits every cited
evidence path against the deterministic inventory. Unverified or hallucinated paths are flagged with
`EvidenceStatus.NOT_IN_INVENTORY`, annotated with descriptive validation notes, and trigger finding
confidence downgrades rather than silent acceptance.

Testing LLM-integrated software must not require external network requests or vendor API credentials.
A deterministic `FakeAgentRuntime` enables comprehensive offline testing of parsing, tool limits,
evidence validation, CLI options, and representative migration findings. Live provider tests are isolated
behind explicit opt-in markers. Remote trace exports are disabled by default for privacy and local safety.
