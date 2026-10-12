"""Git-native knowledge adapter storing challenges, solutions, learnings, and ADRs in .agent/."""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.domain.knowledge import (
    ArchitecturalDecisionRecord,
    CandidateSolution,
    ChallengeRecord,
    CuratedLearning,
)
from migration_agent.ports.knowledge import KnowledgePort

T = TypeVar("T", bound=BaseModel)


class GitKnowledgeAdapter(KnowledgePort):
    """Stores and loads Markdown documents with frontmatter in .agent/ subdirectories."""

    def _resolve_subpath(
        self, project_root: str, subdir: str, item_id: str | None = None, *, create: bool = False
    ) -> Path:
        raw_root = Path(project_root).absolute()
        for parent in (raw_root, *raw_root.parents):
            if parent.is_symlink() or parent.is_junction():
                raise ValueError("KNOWLEDGE_PATH_UNSAFE: roots cannot traverse links.")
        root_path = raw_root.resolve()
        if create:
            root_path.mkdir(parents=True, exist_ok=True)
        if subdir not in {"challenges", "solutions", "learnings", "decisions"}:
            raise ValueError("KNOWLEDGE_PATH_UNSAFE: unknown metadata directory.")
        target_dir = (
            validate_repository_path(root_path, f".agent/{subdir}")
            if root_path.exists()
            else root_path / ".agent" / subdir
        )
        if create:
            target_dir.mkdir(parents=True, exist_ok=True)

        if item_id is not None:
            if "/" in item_id or "\\" in item_id or ".." in item_id:
                raise ValueError(f"Invalid item ID '{item_id}' contains path traversal characters.")
            if not item_id or ":" in item_id or "\x00" in item_id:
                raise ValueError("KNOWLEDGE_PATH_UNSAFE: invalid metadata identifier.")
            file_path = (
                validate_repository_path(root_path, f".agent/{subdir}/{item_id}.md")
                if root_path.exists()
                else target_dir / f"{item_id}.md"
            )
            return file_path

        return target_dir

    @staticmethod
    def _serialize_document(model: BaseModel, title: str, body_markdown: str) -> str:
        meta_json = json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True)
        return f"---\n{meta_json}\n---\n\n# {title}\n\n{body_markdown.strip()}\n"

    @staticmethod
    def _deserialize_document(content: str, model_cls: type[T]) -> T:
        if not content.startswith("---"):
            raise ValueError("Document does not contain frontmatter separator '---'.")
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Malformed frontmatter; closing '---' not found.")
        meta_str = parts[1].strip()
        data = json.loads(meta_str)
        return model_cls.model_validate(data)

    @staticmethod
    def _read(project_root: str, path: Path) -> str:
        root = Path(project_root).resolve()
        return read_repository_text(root, path.relative_to(root).as_posix())

    # --- Challenges ---

    def save_challenge(self, project_root: str, challenge: ChallengeRecord) -> str:
        file_path = self._resolve_subpath(
            project_root, "challenges", challenge.challenge_id, create=True
        )
        body = (
            f"**Category:** {challenge.category}\n"
            f"**Status:** {challenge.status}\n\n"
            f"## Description\n\n{challenge.description}\n"
        )
        if challenge.diagnostic_citations:
            body += "\n## Diagnostics\n\n"
            for diag in challenge.diagnostic_citations:
                body += f"- `{diag}`\n"

        content = self._serialize_document(challenge, challenge.title, body)
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def get_challenge(self, project_root: str, challenge_id: str) -> ChallengeRecord | None:
        file_path = self._resolve_subpath(project_root, "challenges", challenge_id)
        if not file_path.is_file():
            return None
        content = read_repository_text(
            Path(project_root), file_path.relative_to(Path(project_root).resolve()).as_posix()
        )
        return self._deserialize_document(content, ChallengeRecord)

    def list_challenges(self, project_root: str) -> list[ChallengeRecord]:
        directory = self._resolve_subpath(project_root, "challenges")
        if not directory.is_dir():
            return []
        results: list[ChallengeRecord] = []
        for file in sorted(directory.glob("*.md"), key=lambda p: p.stem):
            try:
                content = self._read(project_root, file)
                results.append(self._deserialize_document(content, ChallengeRecord))
            except (ValueError, json.JSONDecodeError):
                continue
        return results

    # --- Solutions ---

    def save_solution(self, project_root: str, solution: CandidateSolution) -> str:
        file_path = self._resolve_subpath(
            project_root, "solutions", solution.solution_id, create=True
        )
        body = (
            f"**Challenge:** `{solution.challenge_id}`\n"
            f"**Status:** {solution.status}\n"
            f"**Verified By Run:** `{solution.verified_by_run_id or 'None'}`\n\n"
            f"## Proposed Approach\n\n{solution.proposed_approach}\n"
        )
        content = self._serialize_document(solution, f"Solution {solution.solution_id}", body)
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def get_solution(self, project_root: str, solution_id: str) -> CandidateSolution | None:
        file_path = self._resolve_subpath(project_root, "solutions", solution_id)
        if not file_path.is_file():
            return None
        content = self._read(project_root, file_path)
        return self._deserialize_document(content, CandidateSolution)

    def list_solutions(self, project_root: str) -> list[CandidateSolution]:
        directory = self._resolve_subpath(project_root, "solutions")
        if not directory.is_dir():
            return []
        results: list[CandidateSolution] = []
        for file in sorted(directory.glob("*.md"), key=lambda p: p.stem):
            try:
                content = self._read(project_root, file)
                results.append(self._deserialize_document(content, CandidateSolution))
            except (ValueError, json.JSONDecodeError):
                continue
        return results

    # --- Curated Learnings ---

    def save_learning(self, project_root: str, learning: CuratedLearning) -> str:
        file_path = self._resolve_subpath(
            project_root, "learnings", learning.learning_id, create=True
        )
        body = (
            f"**Source Challenge:** `{learning.source_challenge_id}`\n"
            f"**Source Solution:** `{learning.source_solution_id}`\n"
            f"**Approved By:** `{learning.approved_by}`\n\n"
            f"## Findings\n\n{learning.findings}\n\n"
            f"## Recommended Pattern\n\n{learning.recommended_pattern}\n"
        )
        if learning.anti_patterns:
            body += "\n## Anti-Patterns\n\n"
            for ap in learning.anti_patterns:
                body += f"- {ap}\n"

        content = self._serialize_document(learning, learning.title, body)
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def get_learning(self, project_root: str, learning_id: str) -> CuratedLearning | None:
        file_path = self._resolve_subpath(project_root, "learnings", learning_id)
        if not file_path.is_file():
            return None
        content = self._read(project_root, file_path)
        return self._deserialize_document(content, CuratedLearning)

    def list_learnings(self, project_root: str) -> list[CuratedLearning]:
        directory = self._resolve_subpath(project_root, "learnings")
        if not directory.is_dir():
            return []
        results: list[CuratedLearning] = []
        for file in sorted(directory.glob("*.md"), key=lambda p: p.stem):
            try:
                content = self._read(project_root, file)
                results.append(self._deserialize_document(content, CuratedLearning))
            except (ValueError, json.JSONDecodeError):
                continue
        return results

    # --- Architectural Decisions (ADRs) ---

    def save_decision(self, project_root: str, decision: ArchitecturalDecisionRecord) -> str:
        file_path = self._resolve_subpath(
            project_root, "decisions", decision.decision_id, create=True
        )
        body = (
            f"**Status:** {decision.status}\n"
            f"**Decided By:** `{decision.decided_by}`\n\n"
            f"## Context\n\n{decision.context}\n\n"
            f"## Decision\n\n{decision.decision}\n\n"
            f"## Consequences\n\n{decision.consequences}\n"
        )
        content = self._serialize_document(
            decision, f"{decision.decision_id}: {decision.title}", body
        )
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def get_decision(
        self, project_root: str, decision_id: str
    ) -> ArchitecturalDecisionRecord | None:
        file_path = self._resolve_subpath(project_root, "decisions", decision_id)
        if not file_path.is_file():
            return None
        content = self._read(project_root, file_path)
        return self._deserialize_document(content, ArchitecturalDecisionRecord)

    def list_decisions(self, project_root: str) -> list[ArchitecturalDecisionRecord]:
        directory = self._resolve_subpath(project_root, "decisions")
        if not directory.is_dir():
            return []
        results: list[ArchitecturalDecisionRecord] = []
        for file in sorted(directory.glob("*.md"), key=lambda p: p.stem):
            try:
                content = self._read(project_root, file)
                results.append(self._deserialize_document(content, ArchitecturalDecisionRecord))
            except (ValueError, json.JSONDecodeError):
                continue
        return results
