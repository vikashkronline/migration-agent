"""Typed boundary for mandatory browser review of the staged application."""

from collections.abc import Callable
from typing import Protocol

from migration_agent.domain.browser_validation import BrowserEvidence
from migration_agent.domain.execution import ExecutionProvenance
from migration_agent.domain.host_workflow import WorkflowRecord, WriterLease
from migration_agent.domain.validation import ValidationProfile


class BrowserValidationPort(Protocol):
    required_profiles: frozenset[ValidationProfile]

    def run(
        self,
        record: WorkflowRecord,
        provenance: ExecutionProvenance,
        lease: WriterLease,
        fence: Callable[[], None],
    ) -> BrowserEvidence: ...
    def verify(self, evidence: BrowserEvidence, record: WorkflowRecord) -> None: ...
