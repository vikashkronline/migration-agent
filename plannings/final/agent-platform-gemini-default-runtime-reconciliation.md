# Agent Platform — Gemini-Default Runtime Reconciliation Remarks

> **Purpose:** Targeted amendments to make **Google Gemini the default model/runtime provider** while preserving OpenAI as a supported parallel provider.
>
> **Status:** Apply these changes to the current master plan without reopening unrelated architecture decisions.
>
> **Source Plan:** `agent-platform-master-plan.md`

---

## 1. Final Runtime Provider Decision

The platform must be **LLM-provider neutral at the domain/application boundary** while selecting **Google Gemini as the default configured provider**.

The desired architecture is:

```text
                         AgentRuntimePort
                                |
                  +-------------+-------------+
                  |                           |
          Gemini Runtime Adapter       OpenAI Runtime Adapter
                  |                           |
           Google Gemini API             OpenAI API/SDK
                  |
          DEFAULT PROVIDER
```

The important rule is:

> **Gemini is the default provider; OpenAI remains a first-class alternative provider. Neither provider may become a domain/application dependency.**

---

## 2. Clarify the Role of Antigravity / Codex

The implementation environment used by the engineering/coding agent must not be confused with the runtime provider used by the Agent Platform.

These are separate concerns:

```text
Engineering / coding environment
        Antigravity / Codex / other coding agent
                         |
                         v
              modifies platform source
                         |
                         v
              Agent Platform runtime
                         |
                 AgentRuntimePort
                         |
              +----------+----------+
              |                     |
            Gemini                OpenAI
```

The platform source code must therefore contain no architectural assumption that it will always be developed, maintained, or operated through a particular coding-agent ecosystem.

---

## 3. Replace the OpenAI-Specific Phase 2 Runtime Requirement

The current Phase 2 wording is too provider-specific:

> "Implement the port with the application-hosted OpenAI Agents SDK..."

Replace it with:

> **Implement `AgentRuntimePort` behind a provider-neutral runtime boundary. Make Google Gemini the default configured runtime provider and keep OpenAI as a supported parallel provider. Provider SDK types must not cross the domain/application boundary.**

The Phase 2 implementation must remain limited to the read-only analysis agent.

---

## 4. Gemini Should Be the Default Configuration

Introduce an explicit provider configuration model.

Example:

```json
{
  "agent_runtime": {
    "provider": "gemini",
    "model": "<configured-gemini-model>"
  }
}
```

The exact model name should remain configuration, not hard-coded architecture.

Equivalent environment/configuration support may be provided for local development, but credentials must never be committed to Git.

Recommended environment variables:

```text
GEMINI_API_KEY
OPENAI_API_KEY
```

Provider selection must be explicit and observable in run metadata without persisting secrets.

---

## 5. Provider Adapter Boundary

Use a provider-neutral contract such as:

```text
AgentRuntimePort
ModelRequest
ModelResponse
StructuredOutputSchema
ToolDefinition
RuntimeUsage
RuntimeError
```

Provider-specific implementations remain in infrastructure/orchestration adapters:

```text
infrastructure/
  ai/
    gemini/
      GeminiRuntimeAdapter
    openai/
      OpenAIRuntimeAdapter
```

Do not allow types such as:

```text
google.genai.*
openai.*
openai-agents.*
```

to appear in:

- Domain models
- Domain services
- Application use cases
- `ChangeSet`
- `Run`
- `ContextEnvelope`
- Policy models
- Approval models
- Persistent Git schema

---

## 6. Prefer Native Gemini Integration for the Default Provider

For the Gemini default path, prefer the official Google GenAI SDK/API rather than making the OpenAI compatibility endpoint the architectural foundation.

Google's current documentation recommends calling the Gemini API directly when building a Gemini integration, while the OpenAI compatibility layer is positioned as a low-friction integration path with some feature limitations. citeturn400155search0turn400155search4

This distinction is important:

```text
DEFAULT
GeminiRuntimeAdapter
        |
        v
Official Google GenAI SDK/API
```

rather than making:

```text
Gemini
  ^
  |
OpenAI-compatible translation layer
  ^
  |
OpenAI-specific architecture
```

the permanent design.

The OpenAI-compatible Gemini endpoint may still be used as a compatibility adapter when useful, but it must not define the platform's core runtime contract.

---

## 7. Pydantic Structured Output Remains the Contract

The existing Pydantic requirement should remain.

Gemini's current official SDK supports structured JSON output using schemas derived from Pydantic models, which aligns directly with the platform's typed analysis-result requirement. citeturn400155search1turn400155search3

Therefore Phase 2 should continue requiring:

```text
LLM response
     |
     v
Structured JSON
     |
     v
Pydantic validation
     |
     v
Deterministic evidence validation
     |
     v
Typed analysis findings
```

The model provider never becomes the source of truth for evidence.

---

## 8. Update the Phase 2 Model Configuration

Replace wording equivalent to:

> "Keep the model name configurable through `MIGRATION_AGENT_MODEL`."

with a provider-aware configuration:

```text
AGENT_RUNTIME_PROVIDER=gemini
AGENT_RUNTIME_MODEL=<configured-model>
```

Optionally retain provider-specific aliases for compatibility, but the canonical configuration should represent both provider and model.

Example:

```text
AGENT_RUNTIME_PROVIDER=gemini
AGENT_RUNTIME_MODEL=<gemini-model>
```

or:

```text
AGENT_RUNTIME_PROVIDER=openai
AGENT_RUNTIME_MODEL=<openai-model>
```

The default is always:

```text
AGENT_RUNTIME_PROVIDER=gemini
```

unless explicitly overridden.

---

## 9. Offline Testing Requirement

The existing deterministic fake runtime remains mandatory.

Normal tests must not require:

- Gemini credentials
- OpenAI credentials
- Network access
- Live model inference

The test architecture should be:

```text
AgentRuntimePort
       |
       +--> FakeRuntimeAdapter   <-- normal tests
       |
       +--> GeminiRuntimeAdapter <-- opt-in integration tests
       |
       +--> OpenAIRuntimeAdapter <-- opt-in integration tests
```

This preserves the existing requirement that normal tests remain deterministic and offline.

---

## 10. Provider-Specific Integration Tests

Add explicit provider conformance tests.

Each runtime adapter should be validated against the same application-level contract:

```text
Given:
  Typed request
  Pydantic output schema
  Bounded tools
  Runtime policy

Expect:
  Typed response
  Valid structured output
  Usage metadata where available
  Deterministic error mapping
  No provider-specific leakage into application types
```

At minimum:

- Gemini integration test
- OpenAI integration test
- Fake runtime test

Live provider tests remain opt-in and must never be part of the default offline test suite.

---

## 11. Runtime Selection and Failover

Do **not** introduce automatic provider failover in Phase 2.

Provider selection should be explicit.

For example:

```text
agent analyze
        |
        v
Configured provider = Gemini
        |
        v
GeminiRuntimeAdapter
```

If Gemini fails, the run should produce a typed runtime failure rather than silently switching to OpenAI.

Automatic cross-provider fallback can be considered in a later phase only after defining its effects on:

- reproducibility
- cost
- data residency/transmission
- model behavior
- approval/provenance
- auditability
- evaluation comparability

A provider switch should always be visible in run metadata.

---

## 12. Provenance and Audit Requirements

Every model-backed run should record non-secret provider metadata such as:

```text
provider
model
runtime_adapter_version
request_schema_version
response_schema_version
```

The platform must not persist:

- API keys
- Authorization headers
- Raw credential material
- Unbounded prompt/context payloads
- Provider secrets

This complements the existing event-data classification rules.

---

## 13. Extend the Architecture Invariant

Add an explicit invariant:

> **LLM Provider Neutrality:** No core domain or application contract may depend on a specific model provider, SDK, or provider-specific orchestration framework. Provider integrations are infrastructure adapters behind `AgentRuntimePort`. The default provider is configuration, not architecture.

This should sit alongside the existing invariant that the core domain does not directly depend on an LLM provider.

---

## 14. ADR Update

Update the relevant ADR/runtime decision to state:

```text
LLM Runtime Provider Strategy

The platform exposes a provider-neutral AgentRuntimePort.

Google Gemini is the default configured runtime provider.

OpenAI is supported as a parallel first-class provider through a separate
adapter.

The official Gemini API/SDK is the preferred implementation path for the
Gemini adapter. Compatibility endpoints may be used where appropriate but
must not become the core abstraction.

Provider-specific SDK types never cross domain/application boundaries.

Provider selection is explicit, auditable, and configuration-driven.
Automatic cross-provider failover is deferred.
```

---

## 15. Phase 2 Updated Implementation Direction

Phase 2 should conceptually become:

```text
Phase 2
  |
  +-- AgentRuntimePort
  |
  +-- GeminiRuntimeAdapter (DEFAULT)
  |
  +-- OpenAIRuntimeAdapter (PARALLEL)
  |
  +-- FakeRuntimeAdapter (OFFLINE TESTS)
  |
  +-- One read-only analysis agent
  |
  +-- Pydantic structured output
  |
  +-- Deterministic evidence validation
```

Do not add:

- Specialist agents
- Multi-agent handoffs
- Autonomous mutation
- Automatic provider failover
- Provider-specific domain logic
- Remote Agents API dependency
- GUI work
- Later-phase migration execution

---

## 16. Things NOT to Change

Do not reopen:

- Project neutrality
- `AgentRuntimePort`
- Deterministic Phase 1 discovery
- Read-only Phase 2 behavior
- Pydantic typed outputs
- Fake runtime testing
- Evidence validation
- Policy Engine architecture
- Git-native authorization
- SQLite/JSONL state model
- ChangeSet safety model
- Angular 21 LTS
- Bootstrap 5.3.x utilities only
- Mermaid architecture rendering
- Local loopback Control API
- Phased implementation order

The Gemini change is a **runtime-provider refinement**, not a change to the platform's domain architecture.

---

## 17. Final Runtime Decision

The final intended configuration is:

| Concern | Decision |
|---|---|
| Runtime abstraction | **`AgentRuntimePort`** |
| Default provider | **Google Gemini** |
| Default integration | **Official Google GenAI SDK/API** |
| Parallel provider | **OpenAI** |
| Provider compatibility layer | Optional adapter, not architectural foundation |
| Normal tests | **Deterministic fake runtime, offline** |
| Live provider tests | **Opt-in only** |
| Automatic provider failover | **Deferred** |
| Provider selection | **Explicit configuration** |
| Secrets | **Environment/user secret store only; never Git** |
| Domain dependency on provider SDKs | **Prohibited** |
| Antigravity/Codex dependency | **Not part of platform architecture** |

### Final architectural principle

> **The platform is provider-neutral, Gemini-default, and OpenAI-compatible by design.**

Gemini should be the default operational path without making Gemini—or OpenAI—the architectural center of gravity.
