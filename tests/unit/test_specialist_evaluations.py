"""Unit tests for specialist comparative evaluation harness."""

from pathlib import Path

from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
)
from migration_agent.application.evaluation import EvaluationService
from migration_agent.application.inventory import InventoryService
from migration_agent.application.specialists import SpecialistCoordinator
from migration_agent.domain import EvaluationBenchmark
from migration_agent.ports import FrameworkAdapterRegistry


def test_specialist_benchmark_ember_mini() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    frameworks = FrameworkAdapterRegistry(
        (EmberClassicAdapter(), AngularAdapter(), AngularJsDirectiveAdapter())
    )
    inv_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=frameworks,
    )
    runtime = FakeAgentRuntime()
    coordinator = SpecialistCoordinator(runtime)
    eval_service = EvaluationService(
        inventory_service=inv_service,
        specialist_coordinator=coordinator,
    )

    benchmark = EvaluationBenchmark.default_ember_mini(str(fixture_path))
    result, specialist_metric = eval_service.run_specialist_benchmark(
        benchmark, fixture_path=fixture_path
    )

    assert result.metrics.passed is True
    assert result.metrics.f1_score == 1.0
    assert specialist_metric.turns_used >= 2
    assert specialist_metric.cost_usd > 0.0
    assert specialist_metric.plan_critique_score is not None
    assert specialist_metric.plan_critique_score >= 0.8
    assert specialist_metric.improvement_detected is True
    assert "## Specialist Subagent Telemetry" in result.summary


def test_specialist_benchmark_angularjs_mini() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    frameworks = FrameworkAdapterRegistry(
        (EmberClassicAdapter(), AngularAdapter(), AngularJsDirectiveAdapter())
    )
    inv_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=frameworks,
    )
    runtime = FakeAgentRuntime()
    coordinator = SpecialistCoordinator(runtime)
    eval_service = EvaluationService(
        inventory_service=inv_service,
        specialist_coordinator=coordinator,
    )

    benchmark = EvaluationBenchmark.default_angularjs_mini(str(fixture_path))
    result, specialist_metric = eval_service.run_specialist_benchmark(
        benchmark, fixture_path=fixture_path
    )

    assert result.metrics.passed is True
    assert result.metrics.f1_score == 1.0
    assert specialist_metric.turns_used >= 2
    assert specialist_metric.cost_usd > 0.0
    assert specialist_metric.plan_critique_score is not None
    assert specialist_metric.plan_critique_score >= 0.8
    assert specialist_metric.improvement_detected is True
    assert "## Specialist Subagent Telemetry" in result.summary
