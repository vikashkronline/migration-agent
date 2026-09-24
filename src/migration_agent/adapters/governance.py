"""Git-native governance adapter managing .agent/ manifest, policies, and plan exports."""

from pathlib import Path

from migration_agent.domain import MigrationPlan, compute_canonical_digest
from migration_agent.ports import GovernancePort, ProjectManifest, ProjectPolicy


class GitGovernanceAdapter(GovernancePort):
    """Manages platform governance assets in target repository's .agent/ folder."""

    def _resolve_agent_dir(self, project_root: str) -> Path:
        root_path = Path(project_root).resolve()
        agent_dir = root_path / ".agent"
        # Prevent traversal
        if not str(agent_dir).startswith(str(root_path)):
            raise ValueError(f"Target path '{agent_dir}' escapes project root '{root_path}'.")
        return agent_dir

    def ensure_governance_layout(self, project_root: str, project_id: str | None = None) -> None:
        """Ensure .agent/ layout exists with manifest and default policy."""
        agent_dir = self._resolve_agent_dir(project_root)
        agent_dir.mkdir(parents=True, exist_ok=True)
        plans_dir = agent_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        manifest_file = agent_dir / "manifest.json"
        if not manifest_file.exists():
            resolved_id = project_id or Path(project_root).resolve().name
            manifest = ProjectManifest(project_id=resolved_id)
            manifest_file.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        policy_file = agent_dir / "policy.json"
        if not policy_file.exists():
            policy = ProjectPolicy()
            policy_file.write_text(policy.model_dump_json(indent=2), encoding="utf-8")

    def get_policy(self, project_root: str) -> ProjectPolicy:
        """Load project safety policy from .agent/policy.json, creating default if absent."""
        agent_dir = self._resolve_agent_dir(project_root)
        policy_file = agent_dir / "policy.json"
        if not policy_file.exists():
            self.ensure_governance_layout(project_root)
        content = policy_file.read_text(encoding="utf-8")
        return ProjectPolicy.model_validate_json(content)

    def get_policy_digest(self, project_root: str) -> str:
        """Calculate the RFC 8785 canonical digest of the active project policy."""
        policy = self.get_policy(project_root)
        return compute_canonical_digest(policy.model_dump(mode="json"))

    def export_plan(self, project_root: str, plan: MigrationPlan) -> str:
        """Export migration plan to .agent/plans/<plan_id>.json."""
        agent_dir = self._resolve_agent_dir(project_root)
        plans_dir = agent_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        target_file = plans_dir / f"{plan.plan_id}.json"
        target_file.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        return str(target_file)

    def load_plan(self, project_root: str, plan_id: str) -> MigrationPlan | None:
        """Load an exported migration plan from .agent/plans/<plan_id>.json."""
        agent_dir = self._resolve_agent_dir(project_root)
        target_file = agent_dir / "plans" / f"{plan_id}.json"
        if not target_file.exists():
            return None
        content = target_file.read_text(encoding="utf-8")
        return MigrationPlan.model_validate_json(content)
