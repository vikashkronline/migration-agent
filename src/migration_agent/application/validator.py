"""Rule-based migration plan validation and dependency DAG ordering."""

from collections import defaultdict, deque
from dataclasses import dataclass, field

from migration_agent.domain import EvidenceStatus, MigrationPlan, MigrationStep, ProjectInventory


@dataclass
class PlanValidationResult:
    """Outcome of rule-based validation on a migration plan."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RuleBasedPlanValidator:
    """Deterministic validator enforcing structural rules, dependencies, and limits."""

    def __init__(self, max_step_files: int = 10) -> None:
        self.max_step_files = max_step_files

    def validate(
        self,
        plan: MigrationPlan,
        inventory: ProjectInventory | None = None,
    ) -> PlanValidationResult:
        """Run all rule-based checks on a migration plan."""
        errors: list[str] = []
        warnings: list[str] = []

        if not plan.steps:
            errors.append("Migration plan must contain at least one step.")
            return PlanValidationResult(is_valid=False, errors=errors, warnings=warnings)

        step_ids = set()
        for step in plan.steps:
            if step.step_id in step_ids:
                errors.append(f"Duplicate step ID '{step.step_id}' found in plan.")
            step_ids.add(step.step_id)

        # Build dependency graph
        graph: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {s.step_id: 0 for s in plan.steps}

        known_files = {f.path for f in inventory.files} if inventory else None

        for step in plan.steps:
            # Check validation strategy
            valid_strategies = [v.strip() for v in step.validation_strategy if v.strip()]
            if not valid_strategies:
                errors.append(f"Step '{step.step_id}' has no validation strategy defined.")

            # Check size limits
            if len(step.expected_files) > self.max_step_files:
                errors.append(
                    f"Step '{step.step_id}' exceeds maximum expected files "
                    f"({len(step.expected_files)} > {self.max_step_files})."
                )
            if len(step.target_files) > self.max_step_files:
                errors.append(f"Step '{step.step_id}' exceeds maximum declared target files.")

            # Check evidence against inventory
            if known_files is not None:
                for ev in step.evidence:
                    if ev.status == EvidenceStatus.NOT_IN_INVENTORY or ev.path not in known_files:
                        errors.append(
                            f"Step '{step.step_id}' references invalid or missing evidence "
                            f"path '{ev.path}'."
                        )

            # Check dependencies
            for dep in step.dependencies:
                if dep == step.step_id:
                    errors.append(f"Step '{step.step_id}' cannot depend on itself.")
                elif dep not in step_ids:
                    errors.append(f"Step '{step.step_id}' depends on non-existent step '{dep}'.")
                else:
                    graph[dep].append(step.step_id)
                    in_degree[step.step_id] += 1

        # Cycle detection using Kahn's algorithm
        queue = deque([sid for sid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count < len(plan.steps):
            cycle_steps = sorted([sid for sid, deg in in_degree.items() if deg > 0])
            errors.append(f"Dependency cycle detected involving step(s): {', '.join(cycle_steps)}.")

        return PlanValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def topological_sort(self, steps: list[MigrationStep]) -> list[MigrationStep]:
        """Order migration steps such that dependencies appear before dependents.

        Deterministic tie-breaking uses step_id.
        Raises ValueError if dependency cycle or unknown dependency is encountered.
        """
        step_map = {step.step_id: step for step in steps}
        graph: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {s.step_id: 0 for s in steps}

        for step in steps:
            for dep in step.dependencies:
                if dep not in step_map:
                    raise ValueError(f"Step '{step.step_id}' depends on unknown step '{dep}'.")
                if dep == step.step_id:
                    raise ValueError(f"Step '{step.step_id}' cannot depend on itself.")
                graph[dep].append(step.step_id)
                in_degree[step.step_id] += 1

        # Deterministic queue with tie-breaking
        ready = sorted([sid for sid, deg in in_degree.items() if deg == 0])
        ordered_ids: list[str] = []

        while ready:
            curr = ready.pop(0)
            ordered_ids.append(curr)
            for neighbor in sorted(graph[curr]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    ready.append(neighbor)
                    ready.sort()

        if len(ordered_ids) < len(steps):
            unresolved = sorted([sid for sid, deg in in_degree.items() if deg > 0])
            raise ValueError(f"Dependency cycle detected involving: {', '.join(unresolved)}")

        return [step_map[sid] for sid in ordered_ids]
