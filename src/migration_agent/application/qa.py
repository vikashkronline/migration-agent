"""Contextual Q&A application service consuming ContextEnvelope (Master Plan Section 6)."""

from pathlib import Path

from migration_agent.application.inventory import InventoryService
from migration_agent.domain.analysis import EvidenceReference, EvidenceStatus
from migration_agent.domain.qa import (
    ContextEnvelope,
    ContextualAnswer,
    ContextualQARequest,
)
from migration_agent.ports.agent_runtime import AgentRuntimePort
from migration_agent.ports.governance import GovernancePort
from migration_agent.ports.knowledge import KnowledgePort


class ContextualQAService:
    """Coordinates context-bounded technical inquiries across inventory, ADRs, and learnings."""

    def __init__(
        self,
        runtime: AgentRuntimePort,
        knowledge_port: KnowledgePort,
        governance_port: GovernancePort,
        inventory_service: InventoryService | None = None,
    ) -> None:
        self._runtime = runtime
        self._knowledge = knowledge_port
        self._governance = governance_port
        self._inventory = inventory_service

    def ask(
        self,
        project_root: str,
        query: str,
        *,
        selected_entity: str | None = None,
        selected_artifact: str | None = None,
        current_run_id: str | None = None,
        provider: str = "gemini",
        model: str | None = None,
        dry_run: bool = True,
    ) -> ContextualAnswer:
        """Process a contextual question, bounding the prompt within a typed ContextEnvelope."""
        root_path = Path(project_root).resolve()

        # 1. Collect knowledge references
        decisions = self._knowledge.list_decisions(str(root_path))
        decision_ids = tuple(d.decision_id for d in decisions)

        learnings = self._knowledge.list_learnings(str(root_path))
        learning_ids = tuple(lrn.learning_id for lrn in learnings)

        # 2. Collect policy digest
        policy_digest = self._governance.get_policy_digest(str(root_path))

        # 3. Collect inventory context
        eligible_paths: set[str] = set()
        evidence_refs: list[EvidenceReference] = []

        if self._inventory is not None and root_path.is_dir():
            try:
                inv = self._inventory.inventory(root_path)
                eligible_paths = {f.path for f in inv.files}
                for f in inv.files[:5]:
                    evidence_refs.append(
                        EvidenceReference(
                            path=f.path,
                            description=f"Inventory file ({f.category.value})",
                        )
                    )
            except Exception:
                pass

        # 4. Build ContextEnvelope
        envelope = ContextEnvelope(
            project_root=str(root_path),
            query=query.strip(),
            selected_entity=selected_entity,
            selected_artifact=selected_artifact,
            current_run_id=current_run_id,
            relevant_decisions=decision_ids,
            relevant_learnings=learning_ids,
            evidence_references=tuple(evidence_refs),
            active_policy_digest=policy_digest,
        )

        # 5. Dispatch to runtime
        qa_request = ContextualQARequest(
            envelope=envelope,
            provider=provider,
            model=model or "default",
            dry_run=dry_run,
        )
        raw_answer = self._runtime.ask(qa_request)

        # 6. Audit citations against repository inventory (Invariant 1: model is untrusted proposer)
        audited_citations: list[EvidenceReference] = []
        for citation in raw_answer.citations:
            is_valid = citation.path in eligible_paths or (root_path / citation.path).exists()
            status = EvidenceStatus.VALID if is_valid else EvidenceStatus.NOT_IN_INVENTORY
            audited_citations.append(
                citation.model_copy(
                    update={
                        "status": status,
                        "validation_note": (
                            "Verified in repository inventory."
                            if is_valid
                            else f"Citation path '{citation.path}' not found in target repository."
                        ),
                    }
                )
            )

        return raw_answer.model_copy(update={"citations": tuple(audited_citations)})
