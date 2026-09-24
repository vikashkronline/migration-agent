"""Application service for running offline evaluation benchmarks and reporting metrics."""

import time
import uuid
from pathlib import Path

from migration_agent.application.analysis import AnalysisService
from migration_agent.application.inventory import InventoryService
from migration_agent.application.transformation import TransformationService
from migration_agent.domain import (
    EvaluationBenchmark,
    EvaluationMetric,
    EvaluationResult,
    FindingCategory,
)


class EvaluationService:
    """Evaluates transformation and analysis accuracy against synthetic ground truth."""

    def __init__(
        self,
        inventory_service: InventoryService | None = None,
        analysis_service: AnalysisService | None = None,
        transformation_service: TransformationService | None = None,
    ) -> None:
        self.inventory_service = inventory_service
        self.analysis_service = analysis_service
        self.transformation_service = transformation_service

    def run_benchmark(
        self,
        benchmark: EvaluationBenchmark,
        *,
        run_id: str | None = None,
        fixture_path: Path | str | None = None,
    ) -> EvaluationResult:
        """Execute ground-truth benchmark and compute precision, recall, and F1 score."""
        target_dir = Path(fixture_path or benchmark.target_fixture).resolve()
        effective_run_id = run_id or f"eval-{uuid.uuid4().hex[:8]}"
        start_time = time.monotonic()

        detected: set[str] = set()
        repair_count = 0

        # Step 1: Detect components via analysis service if available
        if self.analysis_service is not None:
            _, analysis = self.analysis_service.analyze(
                target_dir,
                provider="gemini",
                model="gemini-2.5-pro",
                dry_run=True,
            )
            for finding in analysis.findings:
                if finding.category == FindingCategory.COMPONENT:
                    comp_name = finding.id.removeprefix("finding-component-")
                    if not comp_name.endswith("-test"):
                        detected.add(comp_name)
        elif self.inventory_service is not None:
            inventory = self.inventory_service.inventory(target_dir)
            for f in inventory.files:
                if (
                    not f.path.startswith("tests/")
                    and not f.path.endswith(("-test.js", "-test.ts", ".spec.js", ".spec.ts"))
                    and (f.path.endswith(".js") or f.path.endswith(".ts"))
                ):
                    if "components/" in f.path:
                        detected.add(Path(f.path).stem)
                    elif ".directive." in f.path or f.path.endswith(".directive.js"):
                        detected.add(
                            Path(f.path)
                            .name.replace(".directive.js", "")
                            .replace(".directive.ts", "")
                        )
        else:
            # Fallback direct filesystem discovery for minimal tests
            comp_dir = target_dir / "app" / "components"
            if comp_dir.exists():
                for p in comp_dir.glob("*.js"):
                    detected.add(p.stem)
            for p in target_dir.rglob("*.directive.js"):
                detected.add(p.name.replace(".directive.js", ""))

        # Step 2: Calculate evaluation metrics against benchmark ground truth
        expected = set(benchmark.expected_components)
        true_positives = detected & expected
        false_positives = detected - expected
        false_negatives = expected - detected

        precision = (
            len(true_positives) / len(detected) if detected else (1.0 if not expected else 0.0)
        )
        recall = len(true_positives) / len(expected) if expected else 1.0
        f1 = (
            (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0.0 else 0.0
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)
        passed = precision >= benchmark.min_precision and recall >= benchmark.min_recall

        detected_tuple = tuple(sorted(detected))
        missed_tuple = tuple(sorted(false_negatives))
        unexpected_tuple = tuple(sorted(false_positives))

        summary_md = (
            f"# Benchmark Evaluation: {benchmark.name}\n\n"
            f"- **Benchmark ID**: `{benchmark.benchmark_id}`\n"
            f"- **Status**: {'PASSED' if passed else 'FAILED'}\n"
            f"- **Precision**: {precision:.2f} (threshold: {benchmark.min_precision:.2f})\n"
            f"- **Recall**: {recall:.2f} (threshold: {benchmark.min_recall:.2f})\n"
            f"- **F1 Score**: {f1:.2f}\n"
            f"- **Repair Count**: {repair_count}\n"
            f"- **Duration**: {duration_ms} ms\n"
            f"- **Detected Components**: {', '.join(detected_tuple) or 'None'}\n"
            f"- **Missed Components**: {', '.join(missed_tuple) or 'None'}\n"
            f"- **Unexpected Components**: {', '.join(unexpected_tuple) or 'None'}\n"
        )

        return EvaluationResult(
            benchmark_id=benchmark.benchmark_id,
            run_id=effective_run_id,
            metrics=EvaluationMetric(
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1_score=round(f1, 4),
                repair_count=repair_count,
                duration_ms=duration_ms,
                passed=passed,
            ),
            detected_components=detected_tuple,
            missed_components=missed_tuple,
            unexpected_components=unexpected_tuple,
            summary=summary_md,
        )
