# Configuration browser verification

The screenshots are produced by `tests/unit/test_configuration_browser.py` using the packaged
production client, real loopback Control API, genuine ephemeral owner signatures and isolated
source/governance/state/staging/trust/preferences directories.

- `models-desktop.png`: successful personal model choice, approved profiles and scope separation.
- `owner-handoff.png`: shared proposal, exact signing digest and trusted terminal arguments.
- `overview-mobile.png`: responsive overview without horizontal overflow.
- `overview-mobile-dark.png`: the same view in dark mode.

The test confirms no external browser requests or page errors, unchanged source fixture bytes,
and no browser-side shared activation. The owner handoff remains an unsigned proposal until the
owner performs the real CLI signing workflow. No credentials or private keys are captured.

The full implementation and quality evidence are documented in
`plannings/agent-configuration-management-implementation-report.md`.
