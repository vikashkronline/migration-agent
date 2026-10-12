"""Architecture context reaches both provider adapters without a live provider call."""

from unittest.mock import Mock, patch

import pytest
from test_planning_service import _sample_analysis, _sample_inventory

from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
from migration_agent.adapters.gemini import GeminiRuntimeAdapter
from migration_agent.adapters.schemas import AgentPlanningOutput
from migration_agent.domain.knowledge import ArchitecturalDecisionRecord
from migration_agent.ports import PlanningRequest


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_provider_planning_includes_accepted_decisions(provider: str) -> None:
    inventory = _sample_inventory()
    request = PlanningRequest(
        inventory=inventory,
        analysis=_sample_analysis(inventory),
        model="offline-model",
        accepted_decisions=(
            ArchitecturalDecisionRecord(
                decision_id="ADR-001",
                title="Architecture baseline",
                context="Migration",
                decision="Keep the legacy source read-only.",
                consequences="Generate into isolated staging.",
                decided_by="operator",
            ),
        ),
    )
    output = AgentPlanningOutput(steps=[])
    if provider == "openai":
        with patch("migration_agent.adapters.agents.Runner.run_sync") as run:
            run.return_value.final_output = output
            assert OpenAIAgentsRuntimeAdapter().plan(request) == []
            prompt = run.call_args.args[1]
            instructions = run.call_args.args[0].instructions
    else:
        with patch("migration_agent.adapters.gemini.genai.Client") as client:
            generate = client.return_value.models.generate_content
            generate.return_value = Mock(parsed=output)
            with patch.object(GeminiRuntimeAdapter, "_get_api_key", return_value="offline-fixture"):
                assert GeminiRuntimeAdapter().plan(request) == []
            prompt = generate.call_args.kwargs["contents"]
            instructions = generate.call_args.kwargs["config"].system_instruction
    assert "ADR-001" in prompt
    assert "Keep the legacy source read-only." in prompt
    assert "take precedence over migration defaults" in instructions
    assert "never permission to bypass safety" in instructions
