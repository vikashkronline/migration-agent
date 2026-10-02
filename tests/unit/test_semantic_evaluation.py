"""Unit tests for semantic evaluation benchmarking (compilation, spec pass, fidelity)."""

from pathlib import Path

from migration_agent.adapters import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
    LocalWorkspaceAdapter,
    SafeFilesystemInspector,
)
from migration_agent.application import EvaluationService, InventoryService, TransformationService
from migration_agent.domain import EvaluationBenchmark
from migration_agent.ports import FrameworkAdapterRegistry


def test_semantic_evaluation_angularjs_directive_mini() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )
    inv_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=registry,
    )
    trans_service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=registry,
        filesystem=SafeFilesystemInspector(),
    )
    eval_service = EvaluationService(
        inventory_service=inv_service,
        transformation_service=trans_service,
    )
    bm = EvaluationBenchmark.default_angularjs_mini(str(fixture_dir))

    result = eval_service.run_benchmark(bm, fixture_path=fixture_dir, semantic=True)

    assert result.metrics.passed is True
    assert result.metrics.f1_score == 1.0
    assert result.metrics.compilation_pass_rate == 1.0
    assert result.metrics.spec_pass_rate == 1.0
    assert result.metrics.control_flow_fidelity == 1.0
    assert "## Semantic Evaluation Metrics" in result.summary
    assert "Compilation Pass Rate" in result.summary
    assert "Control Flow Fidelity" in result.summary


def test_semantic_evaluation_angularjs_realworld_dashboard() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-realworld-dashboard"
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )
    inv_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=registry,
    )
    trans_service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=registry,
        filesystem=SafeFilesystemInspector(),
    )
    eval_service = EvaluationService(
        inventory_service=inv_service,
        transformation_service=trans_service,
    )
    bm = EvaluationBenchmark.default_angularjs_dashboard(str(fixture_dir))

    result = eval_service.run_benchmark(bm, fixture_path=fixture_dir, semantic=True)

    assert result.metrics.passed is True
    assert result.metrics.f1_score >= 0.8
    assert result.metrics.compilation_pass_rate is not None
    assert result.metrics.compilation_pass_rate >= 0.8
    assert result.metrics.spec_pass_rate is not None
    assert result.metrics.spec_pass_rate >= 0.8
    assert result.metrics.control_flow_fidelity is not None
    assert result.metrics.control_flow_fidelity >= 0.8
