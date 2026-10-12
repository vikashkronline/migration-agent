"""Git-native governance adapter managing .agent/ manifest, policies, and plan exports."""

import json
from pathlib import Path

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.domain import MigrationPlan, compute_canonical_digest
from migration_agent.ports import GovernancePort, ProjectManifest, ProjectPolicy
from migration_agent.ports.governance import MigrationSession


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
        """Ensure full .agent/ layout exists with manifest, policy, roles, and knowledge."""
        agent_dir = self._resolve_agent_dir(project_root)
        agent_dir.mkdir(parents=True, exist_ok=True)

        for subdir in [
            "plans",
            "workflows",
            "challenges",
            "solutions",
            "learnings",
            "decisions",
            "access",
        ]:
            (agent_dir / subdir).mkdir(parents=True, exist_ok=True)

        manifest_file = agent_dir / "manifest.json"
        if not manifest_file.exists():
            resolved_id = project_id or Path(project_root).resolve().name
            manifest = ProjectManifest(project_id=resolved_id)
            manifest_file.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        policy_file = agent_dir / "policy.json"
        if not policy_file.exists():
            policy = ProjectPolicy()
            policy_file.write_text(policy.model_dump_json(indent=2), encoding="utf-8")

        config_file = agent_dir / "config.json"
        if not config_file.exists():
            config_file.write_text(
                '{\n  "version": 1,\n  "workflows": {}\n}\n',
                encoding="utf-8",
            )

        roles_file = agent_dir / "access" / "roles.json"
        if not roles_file.exists():
            roles_json = json.dumps(
                {
                    "roles": {
                        "admin": ["*"],
                        "developer": [
                            "project.read",
                            "workflow.execute",
                            "changeset.stage",
                            "changeset.apply",
                            "learning.approve",
                        ],
                        "viewer": ["project.read"],
                    }
                },
                indent=2,
            )
            roles_file.write_text(f"{roles_json}\n", encoding="utf-8")

        principals_file = agent_dir / "access" / "principals.json"
        if not principals_file.exists():
            principals_file.write_text(
                '{\n  "principals": {}\n}\n',
                encoding="utf-8",
            )

        gitignore_file = agent_dir / ".gitignore"
        if not gitignore_file.exists():
            gitignore_file.write_text("local/\n*.tmp\n", encoding="utf-8")

    def get_manifest(self, project_root: str) -> ProjectManifest | None:
        """Load platform project manifest from .agent/manifest.json."""
        manifest_file = validate_repository_path(Path(project_root), ".agent/manifest.json")
        if not manifest_file.exists():
            return None
        content = read_repository_text(Path(project_root), ".agent/manifest.json")
        return ProjectManifest.model_validate_json(content)

    def save_migration_session(self, session: MigrationSession) -> None:
        session.project_root.mkdir(parents=True, exist_ok=True)
        target = validate_repository_path(session.project_root, ".agent/migration-session.json")
        if target.exists():
            existing = MigrationSession.model_validate_json(
                read_repository_text(session.project_root, ".agent/migration-session.json")
            )
            if existing != session:
                raise ValueError(
                    "SESSION_CONFLICT: use a fresh project directory for different roots."
                )
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(session.model_dump_json(indent=2) + "\n")

    def get_policy(self, project_root: str) -> ProjectPolicy:
        """Read project policy without creating governance files in the source."""
        policy_file = validate_repository_path(Path(project_root), ".agent/policy.json")
        if not policy_file.exists():
            return ProjectPolicy()
        content = read_repository_text(Path(project_root), ".agent/policy.json")
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
        if not plan_id or any(c in plan_id for c in ("..", "/", "\\", "\x00", ":")):
            raise ValueError("INVALID_PLAN_ID: invalid plan identifier.")
        relative_path = f".agent/plans/{plan_id}.json"
        target_file = validate_repository_path(Path(project_root), relative_path)
        if not target_file.exists():
            return None
        content = read_repository_text(Path(project_root), relative_path)
        return MigrationPlan.model_validate_json(content)
