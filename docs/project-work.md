# Optional project-work definition

The common Control Center can read `.agent/project-work.json` from the selected
repository. This optional, typed, Git-owned declaration supplies objectives,
foundation/module/knowledge groups, tasks, owners, acceptance criteria and planning
dependencies. The GUI reads it; it does not create or edit it. Without a definition,
existing canonical workflow records remain available and unknown readiness stays
explicit. Invalid definitions show a warning without hiding those records.

The [JSON schema](project-work.schema.json) is generated from the domain model.
For example, replace the sample workflow identities below with existing records:

```json
{
  "schema_version": 1,
  "project_name": "Sample application",
  "objective": "Deliver a verified account experience",
  "items": [
    {
      "item_id": "shared-services",
      "section": "foundation",
      "kind": "group",
      "title": "Shared services",
      "order": 10
    },
    {
      "item_id": "authentication",
      "parent_id": "shared-services",
      "kind": "task",
      "title": "Authentication service",
      "declared_status": "PLANNED",
      "owner": "Platform team",
      "acceptance": ["Protected routes enforce the session boundary"]
    },
    {
      "item_id": "account-module",
      "section": "work",
      "kind": "group",
      "title": "Account module",
      "order": 20
    },
    {
      "item_id": "account-component",
      "parent_id": "account-module",
      "kind": "task",
      "title": "Account component",
      "dependencies": ["authentication"],
      "workflow": {"workflow_id": "existing-plan-id", "task_id": "existing-step-id"}
    }
  ]
}
```

Top-level items choose `foundation`, `work` or `knowledge`; nested ownership places
their descendants. Groups may nest, but only tasks can link workflow evidence.
Identifiers are unique ASCII names beginning with a letter, at most 64 characters;
`project`, `foundation`, `work` and `knowledge` are reserved. Parents must name
declared groups and dependencies must name declared items. Cycles, excessively
deep graphs, duplicate evidence ownership and unknown fields are rejected.
Limits are 1,000 items, 512 KiB per file and 20 criteria/dependencies per item.
Files must pass the existing confined, no-links, secret-screened read boundary.
Do not put credentials or other secrets in this file.

## Progress and authority

A workflow-linked task appears once, with its stable workflow identity, actual
lifecycle, evidence and guarded actions. The declaration adds presentation metadata;
it cannot replace policy, validation, execution dependencies or approval. Declared
planning dependencies appear in the dashboard without rewriting the execution DAG.

An unlinked task shows its declared status and evidence provenance. Even a declared
`COMPLETE` task does not count as verified completion. Verified rollups require the
existing recorded `APPLY_COMPLETED` postconditions. Missing linked evidence remains
inspectable, has no executable actions and keeps the same identity when evidence
arrives. Foundation readiness therefore reflects evidence rather than declarations
or platform health.

Review and commit definitions before staging workflow changes. Editing them after
staging can change the source base and correctly invalidate existing artifacts or
approval. The GUI never writes metadata to repair that drift. Snapshot revisions
include definition changes, so stale details, answers and command confirmations
must reconcile before use.
