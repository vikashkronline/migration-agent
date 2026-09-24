# Phase Status

## Phase 0 — Complete

Scope: initialize the Python project, typed configuration, one domain model, the `doctor`
command, project guidance, and offline quality tooling.

Completed on 2026-09-17 using `uv` 0.12.15 and an isolated CPython 3.12.14
environment. The dependency lock resolved 26 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 26 packages; checked 26 packages.

uv run pytest
7 passed in 0.28s

uv run ruff check .
All checks passed.

uv run ruff format --check .
16 files already formatted.

uv run mypy src
Success: no issues found in 5 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok".
```

The Windows host required the final console-script gate to be launched through
`cmd.exe` because PowerShell denied direct execution of the generated launcher. The
command itself and its result were unchanged. This was a host execution-policy behavior,
not an application failure.

## Phase 1 — Complete

Scope: deterministic read-only repository discovery, typed inventory contracts,
filesystem and framework ports, Ember Classic and Angular evidence adapters, stable JSON
and Markdown reports, an initial threat model, and a synthetic Ember Classic fixture.

Completed on 2026-09-17. The required evidence is:

```text
uv sync --all-groups
Resolved 26 packages; checked 26 packages.

uv run pytest
22 passed in 0.70s

uv run ruff check .
All checks passed.

uv run ruff format --check .
31 files already formatted.

uv run mypy src
Success: no issues found in 15 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok".
```

An inventory smoke run against the checked-in Ember Classic fixture produced six eligible
files, three dependencies, one `ember-classic` fingerprint with four evidence items, no
issues, and both report formats. The original fixture remained unchanged. Tests cover
unknown-framework behavior, Angular evidence, package boundaries, ignored and unsafe
files, binary and size limits, a real symlink escape, output-root overlap, deterministic
serialization, malformed manifests, and secret-name nondisclosure.

## Phase 2 — Complete

Scope: provider-neutral read-only analysis agent behind application-owned `AgentRuntimePort`,
Google Gemini runtime adapter via official `google-genai` SDK as default provider, OpenAI
Agents SDK adapter as parallel provider, bounded read-only repository tools, Pydantic structured
outputs, post-generation deterministic evidence validation, deterministic offline fake runtime,
schema-versioned JSON and Markdown analysis report writer, and `agent analyze` / `migration-agent analyze`
CLI commands with dry-run default.

Completed on 2026-09-25 using `uv` and an isolated CPython 3.12.14 environment. The dependency
lock resolved 69 packages. The required evidence is:

```text
uv sync --all-groups
Resolved 69 packages; checked 69 packages.

uv run pytest
40 passed, 2 skipped in 4.32s

uv run ruff check .
All checks passed!

uv run ruff format --check .
57 files already formatted.

uv run mypy src
Success: no issues found in 22 source files.

uv run migration-agent doctor
Exit code 0; emitted schema-versioned JSON with status "ok" checking google-genai, openai-agents, pydantic, pydantic-settings, typer.
```

An analysis smoke run against the checked-in Ember Classic fixture produced three representative
findings (two component patterns with template/test evidence and one dependency finding),
100% verified evidence paths, zero file mutations, and both `analysis.json` and `analysis.md`
reports. Tests cover domain immutability, post-generation evidence audit, hallucinated path
containment, bounded tool queries and character caps, provider neutrality, fake runtime behavior,
CLI options (`--provider`, `--model`, `--fake-runtime`), and strict layer boundaries.

## Later phases

Phases 3 through 10 have not started. No code transformation, AST modification, validation
runner, run persistence, Git state tiering, or multi-agent implementation exists.
