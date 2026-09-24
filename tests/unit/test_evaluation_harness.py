"""Unit tests for offline evaluation benchmark harness and metric scoring."""

from pathlib import Path

from migration_agent.adapters import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
    FakeAgentRuntime,
    SafeFilesystemInspector,
)
from migration_agent.application import (
    AnalysisService,
    EvaluationService,
    InventoryService,
)
from migration_agent.domain import EvaluationBenchmark
from migration_agent.ports import FrameworkAdapterRegistry


def test_evaluation_benchmark_default_fixture() -> None:
    bm = EvaluationBenchmark.default_ember_mini()
    assert bm.benchmark_id == "bm-ember-classic-mini"
    assert "user-card" in bm.expected_components
    assert bm.min_precision == 0.8
    assert bm.min_recall == 0.8


def test_evaluation_service_with_inventory() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    inventory_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
    )
    eval_service = EvaluationService(inventory_service=inventory_service)
    bm = EvaluationBenchmark.default_ember_mini(str(fixture_dir))

    result = eval_service.run_benchmark(bm, fixture_path=fixture_dir)

    assert result.benchmark_id == bm.benchmark_id
    assert "user-card" in result.detected_components
    assert result.metrics.precision == 1.0
    assert result.metrics.recall == 1.0
    assert result.metrics.f1_score == 1.0
    assert result.metrics.passed is True
    assert "# Benchmark Evaluation:" in result.summary


def test_evaluation_service_with_analysis() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    analysis_service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
        runtime=FakeAgentRuntime(),
    )
    eval_service = EvaluationService(analysis_service=analysis_service)
    bm = EvaluationBenchmark.default_ember_mini(str(fixture_dir))

    result = eval_service.run_benchmark(bm, fixture_path=fixture_dir)

    assert result.metrics.precision == 1.0
    assert result.metrics.recall == 1.0
    assert result.metrics.passed is True


def test_evaluation_service_flags_missed_and_unexpected_components() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    inventory_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
    )
    eval_service = EvaluationService(inventory_service=inventory_service)

    # Synthetic benchmark expecting different components
    bm = EvaluationBenchmark(
        benchmark_id="bm-synthetic",
        name="Synthetic Benchmark",
        target_fixture=str(fixture_dir),
        expected_components=("user-card", "missing-card"),
        min_precision=0.9,
        min_recall=0.9,
    )

    result = eval_service.run_benchmark(bm, fixture_path=fixture_dir)

    assert "missing-card" in result.missed_components
    assert result.metrics.precision == 1.0
    assert result.metrics.recall == 0.5
    assert result.metrics.passed is False


def test_evaluation_service_with_angularjs_directive_fixture() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    inventory_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry(
            (
                EmberClassicAdapter(),
                AngularJsDirectiveAdapter(),
                AngularAdapter(),
            )
        ),
    )
    eval_service = EvaluationService(inventory_service=inventory_service)
    bm = EvaluationBenchmark.default_angularjs_mini(str(fixture_dir))

    result = eval_service.run_benchmark(bm, fixture_path=fixture_dir)

    assert result.benchmark_id == bm.benchmark_id
    assert "user-badge" in result.detected_components
    assert result.metrics.precision == 1.0
    assert result.metrics.recall == 1.0
    assert result.metrics.f1_score == 1.0
    assert result.metrics.passed is True
