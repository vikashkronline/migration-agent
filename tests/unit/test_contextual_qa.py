"""Unit tests for ContextualQAService, ContextEnvelope, ask CLI, and Control API (Phase 12)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from access_fixture import WorkflowAuthorizationFixture
from typer.testing import CliRunner

from migration_agent.adapters import (
    FakeAgentRuntime,
    GitGovernanceAdapter,
    GitKnowledgeAdapter,
)
from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.application import (
    ContextualQAService,
    ControlApiService,
)
from migration_agent.cli import app
from migration_agent.domain import (
    ContextualAnswer,
    EvidenceReference,
    EvidenceStatus,
)

runner = CliRunner()


def test_contextual_qa_bounds_envelope_and_audits_citations(tmp_path: Path) -> None:
    knowledge = GitKnowledgeAdapter()
    governance = GitGovernanceAdapter()
    governance.ensure_governance_layout(str(tmp_path))

    # Add an ADR and a file
    (tmp_path / "valid_file.ts").write_text("export const x = 1;", encoding="utf-8")

    from migration_agent.domain import ArchitecturalDecisionRecord, DecisionStatus, EpistemicStatus

    knowledge.save_decision(
        str(tmp_path),
        ArchitecturalDecisionRecord(
            decision_id="ADR-001",
            title="Use Signals",
            status=DecisionStatus.ACCEPTED,
            context="State management",
            decision="Use Angular Signals",
            consequences="Fast change detection",
            decided_by="engineer",
            epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
        ),
    )

    fake_runtime = FakeAgentRuntime(
        canned_answer=ContextualAnswer(
            query="Where is state stored?",
            answer="State is stored in signals.",
            confidence=0.95,
            citations=(
                EvidenceReference(path="valid_file.ts", description="State definition"),
                EvidenceReference(path="hallucinated_file.ts", description="Hallucination test"),
            ),
        )
    )

    qa_svc = ContextualQAService(
        runtime=fake_runtime,
        knowledge_port=knowledge,
        governance_port=governance,
    )

    answer = qa_svc.ask(str(tmp_path), "Where is state stored?")

    # Verify request envelope recorded
    assert len(fake_runtime.recorded_qa_requests) == 1
    envelope = fake_runtime.recorded_qa_requests[0].envelope
    assert "ADR-001" in envelope.relevant_decisions
    assert envelope.query == "Where is state stored?"

    # Verify citation audit (Invariant 1)
    assert len(answer.citations) == 2
    cit_valid = next(c for c in answer.citations if c.path == "valid_file.ts")
    cit_invalid = next(c for c in answer.citations if c.path == "hallucinated_file.ts")

    assert cit_valid.status == EvidenceStatus.VALID
    assert cit_invalid.status == EvidenceStatus.NOT_IN_INVENTORY


def test_cli_ask_command(tmp_path: Path, cli_workflow_authorization) -> None:
    governance = GitGovernanceAdapter()
    governance.ensure_governance_layout(str(tmp_path))

    result = runner.invoke(
        app,
        [
            "ask",
            "What architecture is used?",
            "--path",
            str(tmp_path),
            "--fake-runtime",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["query"] == "What architecture is used?"
    assert "architecture" in data["answer"].lower()
    assert data["confidence"] == 1.0


def test_control_api_contextual_qa_endpoint(tmp_path: Path) -> None:
    governance = GitGovernanceAdapter()
    governance.ensure_governance_layout(str(tmp_path))
    knowledge = GitKnowledgeAdapter()

    fake_runtime = FakeAgentRuntime(
        canned_answer=ContextualAnswer(
            query="Explain routing",
            answer="Routing uses modern Standalone Routes.",
            confidence=1.0,
        )
    )
    qa_service = ContextualQAService(
        runtime=fake_runtime,
        knowledge_port=knowledge,
        governance_port=governance,
    )
    control_service = ControlApiService(
        governance_port=governance,
        knowledge_port=knowledge,
        qa_service=qa_service,
    )

    broadcaster = MagicMock()
    server = LoopbackControlServer(
        control_service=control_service,
        target_root=tmp_path,
        broadcaster=broadcaster,
        authorization=WorkflowAuthorizationFixture(),
    )

    token = "test-token-1234567890123456"
    server.start(host="127.0.0.1", port=0, session_token=token)
    port = server.server_port

    import urllib.request

    url = f"http://127.0.0.1:{port}/api/v1/contextual-qa"
    payload = json.dumps({"query": "Explain routing"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Session-Token": token,
            "X-CSRF-Token": token,
            "Origin": f"http://127.0.0.1:{port}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["status"] == "ok"
            data = body["data"]
            assert data["query"] == "Explain routing"
            assert "Standalone Routes" in data["answer"]
    finally:
        server.stop()
