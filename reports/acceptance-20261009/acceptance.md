# Separate migration acceptance run — 2026-10-09

Selected read-only source: `C:\Projects\ISOCEL\Alice\Ember\penalite-frontend`.

The separate project is `project/`; its `.agent/migration-session.json` records
absolute source, project, staging and state roots. Operational records are in
`state/`; the declared staging root is `staging/`. Existing initialization and
stores were not reused. The source-isolation ADR is recorded in the external
project through `migration-agent decision record`.

## CLI evidence

- `inventory/inventory.json` and `inventory-after/inventory.json`: 2,269 eligible
  files, detected `ember-classic`, no inventory issues. All eligible paths and
  SHA-256 hashes match between the two runs. Inventory contains 13 feature/pod
  component files and 34 service files.
- `graph/fullstack_inventory.json`: original graph exposed basename collisions,
  returning only three frontend nodes.
- `graph-verified/fullstack_inventory.json`: repaired discovery returns 37
  frontend nodes plus one infrastructure node. All 13 pod component files remain
  represented. JSON and `graph-verified/dependency_graph.mermaid` each contain
  38 distinct node identifiers. Zero discovered edges does not prove independence;
  adapters provide heuristic discovery only.
- `migration-agent validation status`: restricted mode; missing execution backend
  selection and browser validation plan; no execution consents. No repository code
  has been executed through validation.

## Platform fixes

Separate initialization now validates every root pair and records a typed,
idempotent session binding. Planning passes accepted external ADRs to both
provider adapters with architecture precedence. Canonical model configuration is
recognized by doctor, and validation status reports setup prerequisites. Frontend
and Mermaid graph identifiers preserve repeated filenames and punctuation;
conflicting adapter IDs are rejected.

See `docs/end-user-acceptance-hardening.md` in the platform workspace for generic
operations and `docs/phase-status.md` for final quality-gate results. The final
full-suite log is retained in `quality/pytest.log`.

All six required platform gates passed. The full offline Python suite reports
663 passed and 3 skipped in 560.50 seconds. The Control Center test gate reports
21 passed in nine files. These are platform verification results, not target
application migration or validation evidence.

## Outstanding migration work

Automatic approval review rejected live provider analysis before the CLI ran,
because the provider/destination had not been authorized. Provider/model approval
and secure credential provisioning must precede that call. The target architecture
also needs confirmation before its ADR is recorded and foundation generation can
proceed through the platform. Functional tasks follow verified prerequisites.

No target application code was manually authored or generated in this run.
No functional task, native execution consent, ChangeSet approval or source apply
has occurred. The real migration remains incomplete; fake runtime evidence was
used only by platform regression tests.
