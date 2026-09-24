"""Domain models for repeatable offline migration evaluations and benchmark metrics."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class EvaluationMetric(BaseModel):
    """Core benchmark metrics measuring transformation accuracy and autonomy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1_score: float = Field(ge=0.0, le=1.0)
    repair_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    passed: bool


class EvaluationBenchmark(BaseModel):
    """Specification of an offline ground-truth benchmark suite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    target_fixture: str = Field(min_length=1)
    expected_components: tuple[str, ...] = Field(default_factory=tuple)
    expected_files: tuple[str, ...] = Field(default_factory=tuple)
    min_precision: float = Field(default=0.8, ge=0.0, le=1.0)
    min_recall: float = Field(default=0.8, ge=0.0, le=1.0)

    @classmethod
    def default_ember_mini(
        cls, fixture_path: str = "tests/fixtures/ember-classic-mini"
    ) -> "EvaluationBenchmark":
        """Pre-configured ground-truth benchmark for the Ember classic mini fixture."""
        return cls(
            benchmark_id="bm-ember-classic-mini",
            name="Ember Classic Mini Benchmark",
            description=(
                "Evaluates component extraction and transformation accuracy on classic "
                "Ember fixture."
            ),
            target_fixture=fixture_path,
            expected_components=("user-card",),
            expected_files=(
                "src/app/components/user-card/user-card.component.ts",
                "src/app/components/user-card/user-card.component.html",
                "src/app/components/user-card/user-card.component.scss",
                "src/app/components/user-card/user-card.component.spec.ts",
            ),
            min_precision=0.8,
            min_recall=0.8,
        )

    @classmethod
    def default_angularjs_mini(
        cls, fixture_path: str = "tests/fixtures/angularjs-directive-mini"
    ) -> "EvaluationBenchmark":
        """Pre-configured ground-truth benchmark for the AngularJS directive mini fixture."""
        return cls(
            benchmark_id="bm-angularjs-directive-mini",
            name="AngularJS Directive Mini Benchmark",
            description=(
                "Evaluates component extraction and transformation accuracy on AngularJS "
                "directive fixture."
            ),
            target_fixture=fixture_path,
            expected_components=("user-badge",),
            expected_files=(
                "src/app/components/user-badge/user-badge.component.ts",
                "src/app/components/user-badge/user-badge.component.html",
                "src/app/components/user-badge/user-badge.component.scss",
                "src/app/components/user-badge/user-badge.component.spec.ts",
            ),
            min_precision=0.8,
            min_recall=0.8,
        )


class EvaluationResult(BaseModel):
    """Immutable outcome of executing an evaluation benchmark."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    metrics: EvaluationMetric
    detected_components: tuple[str, ...] = Field(default_factory=tuple)
    missed_components: tuple[str, ...] = Field(default_factory=tuple)
    unexpected_components: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str = Field(default="")
