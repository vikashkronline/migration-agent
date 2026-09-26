"""Unit tests for curated project knowledge engine, challenges, solutions, and ADRs (Phase 12)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.adapters import GitKnowledgeAdapter
from migration_agent.application import KnowledgeService
from migration_agent.cli import app
from migration_agent.domain import (
    ChallengeStatus,
    DecisionStatus,
    EpistemicStatus,
    SolutionStatus,
)

runner = CliRunner()


def test_challenge_and_solution_lifecycle(tmp_path: Path) -> None:
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)

    # 1. Record challenge
    ch = service.record_challenge(
        str(tmp_path),
        title="AngularJS scope digest cycle failure",
        description="Nested $scope.$apply causes digest already in progress exception.",
        category="FRAMEWORK_LIFECYCLE",
        diagnostic_citations=("Error: [$rootScope:inprog] $apply already in progress",),
    )
    assert ch.status == ChallengeStatus.OPEN
    assert ch.epistemic_status == EpistemicStatus.OBSERVED

    # Check file written
    ch_file = tmp_path / ".agent" / "challenges" / f"{ch.challenge_id}.md"
    assert ch_file.is_file()
    assert "[$rootScope:inprog]" in ch_file.read_text(encoding="utf-8")

    # 2. List challenges
    challenges = service.list_challenges(str(tmp_path))
    assert len(challenges) == 1
    assert challenges[0].challenge_id == ch.challenge_id

    # 3. Propose candidate solution
    sol = service.propose_solution(
        str(tmp_path),
        challenge_id=ch.challenge_id,
        proposed_approach=(
            "Refactor isolate scope binding to Angular Signals and computed expressions."
        ),
    )
    assert sol.status == SolutionStatus.PROPOSED
    assert sol.challenge_id == ch.challenge_id

    # Check solution file written
    sol_file = tmp_path / ".agent" / "solutions" / f"{sol.solution_id}.md"
    assert sol_file.is_file()

    # 4. Invariant 16: Approve learning requiring human approval
    with pytest.raises(ValueError, match="Invariant 16 violation"):
        service.approve_learning(
            str(tmp_path),
            solution_id=sol.solution_id,
            approved_by="",
            title="Modern Signal Replacement for $scope.$apply",
            findings="Digest loops occur when binding mutable properties across controllers.",
            recommended_pattern="Use signal() and computed() with ChangeDetectionStrategy.OnPush.",
        )

    learning = service.approve_learning(
        str(tmp_path),
        solution_id=sol.solution_id,
        approved_by="lead_engineer@example.com",
        title="Modern Signal Replacement for $scope.$apply",
        findings="Digest loops occur when binding mutable properties across controllers.",
        recommended_pattern="Use signal() and computed() with ChangeDetectionStrategy.OnPush.",
        anti_patterns=("Calling $scope.$apply() inside event listeners",),
        tags=("angular", "signals", "digest-elimination"),
    )
    assert learning.epistemic_status == EpistemicStatus.HUMAN_CONFIRMED
    assert learning.approved_by == "lead_engineer@example.com"

    # Check learning file
    lrn_file = tmp_path / ".agent" / "learnings" / f"{learning.learning_id}.md"
    assert lrn_file.is_file()

    # Check updated statuses of solution and challenge
    updated_sol = service.get_solution(str(tmp_path), sol.solution_id)
    assert updated_sol is not None
    assert updated_sol.status == SolutionStatus.PROMOTED

    updated_ch = service.get_challenge(str(tmp_path), ch.challenge_id)
    assert updated_ch is not None
    assert updated_ch.status == ChallengeStatus.RESOLVED


def test_adr_lifecycle(tmp_path: Path) -> None:
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)

    adr = service.record_decision(
        str(tmp_path),
        decision_id="ADR-042",
        title="Migrate to Standalone Angular Components",
        context="Legacy AngularJS dashboard requires modern component architecture.",
        decision="Refactor all directives to standalone Angular 17+ components.",
        consequences="Eliminates NgModules and enables tree-shakable bundling.",
        decided_by="architect@example.com",
    )
    assert adr.decision_id == "ADR-042"
    assert adr.status == DecisionStatus.ACCEPTED

    adr_file = tmp_path / ".agent" / "decisions" / "ADR-042.md"
    assert adr_file.is_file()

    decisions = service.list_decisions(str(tmp_path))
    assert len(decisions) == 1
    assert decisions[0].decision_id == "ADR-042"


def test_path_traversal_prevention(tmp_path: Path) -> None:
    adapter = GitKnowledgeAdapter()
    with pytest.raises(ValueError, match="traversal"):
        adapter.get_challenge(str(tmp_path), "../secret")

    with pytest.raises(ValueError, match="traversal"):
        adapter.get_decision(str(tmp_path), "ADR/../../etc/passwd")


def test_cli_knowledge_flow(tmp_path: Path) -> None:
    # 1. CLI challenge record
    res_ch = runner.invoke(
        app,
        [
            "challenge",
            "record",
            str(tmp_path),
            "--title",
            "Broken CSS Grid",
            "--desc",
            "Bootstrap 3 grid classes not supported in Bootstrap 5.",
            "--id",
            "ch-css-1",
        ],
    )
    assert res_ch.exit_code == 0
    assert "recorded" in res_ch.stdout

    # 2. CLI challenge list
    res_list = runner.invoke(app, ["challenge", "list", str(tmp_path)])
    assert res_list.exit_code == 0
    assert "ch-css-1" in res_list.stdout

    # 3. CLI solution record
    res_sol = runner.invoke(
        app,
        [
            "solution",
            "record",
            str(tmp_path),
            "--challenge",
            "ch-css-1",
            "--approach",
            "Replace col-xs-* with modern col-* and d-flex gap-*.",
            "--id",
            "sol-css-1",
        ],
    )
    assert res_sol.exit_code == 0
    assert "proposed" in res_sol.stdout

    # 4. CLI learning approve
    res_lrn = runner.invoke(
        app,
        [
            "learning",
            "approve",
            str(tmp_path),
            "--solution",
            "sol-css-1",
            "--approver",
            "alice",
            "--title",
            "Bootstrap 5 Grid Utilities",
            "--findings",
            "col-xs-* is deprecated in BS5.",
            "--pattern",
            "Use col-* and d-flex gap-* utility classes.",
        ],
    )
    assert res_lrn.exit_code == 0
    assert "approved" in res_lrn.stdout

    # 5. CLI decision record
    res_dec = runner.invoke(
        app,
        [
            "decision",
            "record",
            str(tmp_path),
            "--id",
            "ADR-101",
            "--title",
            "Bootstrap 5 Standards",
            "--context",
            "Legacy styling overhaul.",
            "--decision",
            "Enforce Bootstrap 5 utilities.",
            "--consequences",
            "Cleaner HTML templates.",
            "--by",
            "alice",
        ],
    )
    assert res_dec.exit_code == 0
    assert "recorded" in res_dec.stdout
