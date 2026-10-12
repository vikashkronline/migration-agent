"""Contract tests for MCP server protocol negotiation, stream isolation, and read-only tools."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import mcp_types as types
import pytest
from mcp.client._probe import negotiate_auto
from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.mcp import ProjectBinding, create_mcp_server
from migration_agent.config import Settings
from migration_agent.domain.inspection_access import InspectionCapability, InspectionContext
from migration_agent.domain.planning import AssuranceLevel, MigrationPlan, MigrationStep, PlanStatus

FIXTURE_PATH = Path("tests/fixtures/ember-classic-mini").resolve()


@asynccontextmanager
async def create_connected_session(
    binding: ProjectBinding,
    state_dir: Path | None = None,
    inspection_context: InspectionContext | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[tuple[ClientSession, anyio.abc.TaskGroup]]:
    """Helper creating memory stream connected client-server pair."""
    server = create_mcp_server(
        binding=binding,
        state_dir=state_dir,
        inspection_context=inspection_context,
        settings=settings,
    )
    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream[
        SessionMessage | Exception
    ](20)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream[
        SessionMessage
    ](20)

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server._lowlevel_server.run(
                client_to_server_recv,
                server_to_client_send,
                server._lowlevel_server.create_initialization_options(),
            )

        tg.start_soon(run_server)

        async with ClientSession(server_to_client_recv, client_to_server_send) as session:
            with anyio.fail_after(30):
                yield session, tg


@pytest.fixture
def test_binding() -> ProjectBinding:
    return ProjectBinding(FIXTURE_PATH)


@pytest.fixture
def plan_fixture(tmp_path: Path) -> tuple[ProjectBinding, str, SqliteCheckpointStore]:
    """Sets up a test project with an initialized plan in SQLite checkpoints."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    store = SqliteCheckpointStore(state_dir)
    binding = ProjectBinding(FIXTURE_PATH)

    step = MigrationStep(
        step_id="step-1",
        title="Migrate user-card component",
        description="Transform Ember Classic user-card to Angular Standalone",
        expected_files=["app/components/user-card.js", "app/templates/components/user-card.hbs"],
    )
    plan = MigrationPlan(
        plan_id="plan-test-16a",
        source_root=str(FIXTURE_PATH),
        run_id="run-test-16a",
        status=PlanStatus.DRAFT,
        steps=[step],
    )
    store.save_plan(plan)
    return binding, plan.plan_id, store


@pytest.mark.anyio
async def test_protocol_negotiation_legacy_2024(
    test_binding: ProjectBinding, tmp_path: Path
) -> None:
    """Verifies protocol version negotiation for legacy base revision 2024-11-05."""
    async with create_connected_session(test_binding, state_dir=tmp_path) as (session, tg):
        requested_version = "2024-11-05"
        init_res = await session.send_request(
            types.InitializeRequest(
                params=types.InitializeRequestParams(
                    protocol_version=requested_version,
                    capabilities=session._build_capabilities(requested_version),
                    client_info=session._client_info,
                )
            ),
            types.InitializeResult,
        )
        assert init_res.protocol_version == requested_version
        session.adopt(init_res)
        await session.send_notification(types.InitializedNotification())

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        expected = {
            "migration_doctor",
            "migration_inventory",
            "migration_run_status",
            "migration_plan_show",
            "migration_step_preview",
        }
        assert expected.issubset(names)
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_protocol_negotiation_modern_2025(
    test_binding: ProjectBinding, tmp_path: Path
) -> None:
    """Verifies protocol version negotiation for modern revision 2025-03-26."""
    async with create_connected_session(test_binding, state_dir=tmp_path) as (session, tg):
        requested_version = "2025-03-26"
        init_res = await session.send_request(
            types.InitializeRequest(
                params=types.InitializeRequestParams(
                    protocol_version=requested_version,
                    capabilities=session._build_capabilities(requested_version),
                    client_info=session._client_info,
                )
            ),
            types.InitializeResult,
        )
        assert init_res.protocol_version == requested_version
        session.adopt(init_res)
        await session.send_notification(types.InitializedNotification())

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert "migration_doctor" in names
        assert "migration_inventory" in names
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_protocol_negotiation_modern_2026(
    test_binding: ProjectBinding, tmp_path: Path
) -> None:
    """Verifies protocol version negotiation for latest modern revision 2026-07-28."""
    async with create_connected_session(test_binding, state_dir=tmp_path) as (session, tg):
        await negotiate_auto(session)
        assert session.protocol_version == "2026-07-28"

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        expected = {
            "migration_doctor",
            "migration_inventory",
            "migration_run_status",
            "migration_plan_show",
            "migration_step_preview",
        }
        assert expected.issubset(names)

        # Call doctor tool under 2026-07-28
        doc_res = await session.call_tool("migration_doctor", {})
        assert not doc_res.is_error
        assert len(doc_res.content) > 0
        data = json.loads(doc_res.content[0].text)  # type: ignore[attr-defined]
        assert data["status"] == "ok"
        assert data["schema_version"] == 1
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_tool_discovery_and_schema_validation(
    test_binding: ProjectBinding, tmp_path: Path
) -> None:
    """Verifies that tools/list publishes well-formed JSON Schema definitions for all tools."""
    async with create_connected_session(test_binding, state_dir=tmp_path) as (session, tg):
        await session.initialize()
        tool_list = await session.list_tools()
        tools_by_name = {t.name: t for t in tool_list.tools}

        assert len(tools_by_name) == 24
        assert {
            "migration_implementation_context",
            "migration_submit_implementation",
        } <= tools_by_name.keys()
        assert {
            "migration_configuration_show",
            "migration_configuration_propose",
            "migration_configuration_check",
            "migration_configuration_check_status",
        } <= tools_by_name.keys()
        assert not any(name in tools_by_name for name in {"approve", "migration_sign_approval"})

        # Check migration_doctor
        doctor_tool = tools_by_name["migration_doctor"]
        assert "diagnostics" in doctor_tool.description.lower()
        assert doctor_tool.input_schema["type"] == "object"

        # Check migration_inventory
        inv_tool = tools_by_name["migration_inventory"]
        assert "inventory" in inv_tool.description.lower()
        assert "project_id" in inv_tool.input_schema["properties"]

        # Check migration_run_status
        run_tool = tools_by_name["migration_run_status"]
        assert "run_id" in run_tool.input_schema["properties"]
        assert "project_id" in run_tool.input_schema["properties"]
        assert set(run_tool.input_schema.get("required", [])) == {"project_id", "run_id"}

        # Check migration_plan_show
        plan_tool = tools_by_name["migration_plan_show"]
        assert "plan_id" in plan_tool.input_schema["properties"]
        assert "project_id" in plan_tool.input_schema["properties"]
        assert set(plan_tool.input_schema.get("required", [])) == {"project_id", "plan_id"}

        # Check migration_step_preview
        prev_tool = tools_by_name["migration_step_preview"]
        assert "plan_id" in prev_tool.input_schema["properties"]
        assert "step_id" in prev_tool.input_schema["properties"]
        assert "project_id" in prev_tool.input_schema["properties"]
        assert set(prev_tool.input_schema.get("required", [])) == {"project_id", "plan_id"}

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_tool_inventory_execution(test_binding: ProjectBinding, tmp_path: Path) -> None:
    """Verifies migration_inventory execution against the bound ember-classic-mini fixture."""
    async with create_connected_session(test_binding, state_dir=tmp_path) as (session, tg):
        await session.initialize()

        res = await session.call_tool(
            "migration_inventory",
            {"project_id": test_binding.project_id},
        )
        assert not res.is_error
        payload = json.loads(res.content[0].text)  # type: ignore[attr-defined]
        assert payload["status"] == "ok"
        assert payload["project_id"] == test_binding.project_id
        inventory = payload["inventory"]
        assert inventory["schema_version"] == 1
        assert len(inventory["files"]) > 0
        framework_ids = [fw["framework_id"] for fw in inventory["frameworks"]]
        assert "ember-classic" in framework_ids
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_tool_run_status_execution(
    test_binding: ProjectBinding,
    tmp_path: Path,
) -> None:
    """Verifies migration_run_status error on missing run and success on recorded run."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    store = SqliteCheckpointStore(state_dir)

    async with create_connected_session(test_binding, state_dir=state_dir) as (session, tg):
        await session.initialize()

        # Unknown run
        err_res = await session.call_tool(
            "migration_run_status",
            {"project_id": test_binding.project_id, "run_id": "nonexistent-run"},
        )
        assert err_res.is_error
        assert "not found" in err_res.content[0].text.lower()  # type: ignore[attr-defined]

        # Record a run in store
        from datetime import UTC, datetime

        from migration_agent.domain.run_state import ExecutionStep, RunRecord

        store.save_run_record(
            RunRecord(
                run_id="run-12345",
                plan_id="plan-12345",
                source_root=str(test_binding.project_root),
                staging_root=str(tmp_path / "staging"),
                status=ExecutionStep.STAGED,
                current_step_id="step-1",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

        ok_res = await session.call_tool(
            "migration_run_status",
            {"project_id": test_binding.project_id, "run_id": "run-12345"},
        )
        assert not ok_res.is_error
        data = json.loads(ok_res.content[0].text)  # type: ignore[attr-defined]
        assert data["run_id"] == "run-12345"
        assert data["plan_id"] == "plan-12345"
        assert data["status"] == "STAGED"
        assert data["project_id"] == test_binding.project_id

        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_tool_plan_show_and_step_preview(
    plan_fixture: tuple[ProjectBinding, str, SqliteCheckpointStore],
    tmp_path: Path,
) -> None:
    """Verifies migration_plan_show and migration_step_preview for a valid plan."""
    binding, plan_id, store = plan_fixture

    async with create_connected_session(binding, state_dir=store.state_dir) as (session, tg):
        await session.initialize()

        # 1. plan_show
        show_res = await session.call_tool(
            "migration_plan_show",
            {"project_id": binding.project_id, "plan_id": plan_id},
        )
        assert not show_res.is_error
        show_data = json.loads(show_res.content[0].text)  # type: ignore[attr-defined]
        assert show_data["plan_id"] == plan_id
        assert len(show_data["plan"]["steps"]) > 0

        # 2. step_preview
        step_id = show_data["plan"]["steps"][0]["step_id"]
        prev_res = await session.call_tool(
            "migration_step_preview",
            {"project_id": binding.project_id, "plan_id": plan_id, "step_id": step_id},
        )
        assert not prev_res.is_error
        prev_data = json.loads(prev_res.content[0].text)  # type: ignore[attr-defined]
        assert prev_data["plan_id"] == plan_id
        assert prev_data["step_id"] == step_id
        assert prev_data["file_count"] > 0
        assert prev_data["changeset_digest"].startswith("sha256:")
        assert len(prev_data["changeset_digest"]) == 71
        assert len(prev_data["diff"]) > 0

        tg.cancel_scope.cancel()


def test_project_binding_security_defenses(tmp_path: Path) -> None:
    """Verifies that ProjectBinding enforces path containment and rejects invalid inputs."""
    # 1. Non-existent path
    with pytest.raises(ValueError, match="does not exist"):
        ProjectBinding(tmp_path / "does_not_exist")

    # 2. File instead of directory
    file_path = tmp_path / "some_file.txt"
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        ProjectBinding(file_path)

    # 3. Valid binding
    binding = ProjectBinding(FIXTURE_PATH)
    assert binding.project_id.startswith("ember-classic-mini-")
    assert binding.project_root == FIXTURE_PATH

    # 4. Validates project_id match
    binding.validate_project_id(binding.project_id)

    with pytest.raises(ValueError, match="Project ID mismatch"):
        binding.validate_project_id("other-project")

    with pytest.raises(ValueError, match="path traversal"):
        binding.validate_project_id("../escape")

    with pytest.raises(ValueError, match="path traversal"):
        binding.validate_project_id("foo/bar")

    with pytest.raises(ValueError, match="non-empty"):
        binding.validate_project_id("")

    # 5. Path resolution containment
    in_path = binding.resolve_in_project("package.json")
    assert in_path == FIXTURE_PATH / "package.json"

    with pytest.raises(ValueError, match="Path traversal detected"):
        binding.resolve_in_project("../../outside.txt")


def test_subprocess_stdio_stream_isolation_and_secret_redaction(tmp_path: Path) -> None:
    """Verifies process-wide stream isolation, pure JSON stdout, and secret non-disclosure."""
    secret_token = "sk-antigravity-secret-key-9999"
    env = {
        name: os.environ[name]
        for name in ("PATH", "SystemRoot", "TEMP", "TMP", "USERPROFILE", "USERNAME")
        if name in os.environ
    }
    env["OPENAI_API_KEY"] = secret_token
    env["GEMINI_API_KEY"] = secret_token

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "migration_agent.cli",
            "mcp",
            "serve",
            "--project-root",
            str(FIXTURE_PATH),
            "--state-dir",
            str(tmp_path / "state"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    frames: queue.Queue[str] = queue.Queue()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def drain_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            stdout_lines.append(line)
            frames.put(line)

    def drain_stderr() -> None:
        assert proc.stderr is not None
        stderr_lines.extend(proc.stderr)

    readers = [
        threading.Thread(target=drain_stdout, daemon=True),
        threading.Thread(target=drain_stderr, daemon=True),
    ]
    for reader in readers:
        reader.start()

    try:
        # Request 1: Initialize
        req1 = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "contract-test-client", "version": "1.0"},
            },
        }
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(req1) + "\n")
        proc.stdin.flush()

        assert proc.stdout is not None
        line1 = frames.get(timeout=60)
        assert line1.endswith("\n")
        resp1 = json.loads(line1)
        assert resp1["jsonrpc"] == "2.0"
        assert resp1["id"] == 1
        assert resp1["result"]["protocolVersion"] == "2025-03-26"

        # Notification: Initialized
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            + "\n"
        )
        proc.stdin.flush()

        # Request 2: tools/list
        req2 = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        proc.stdin.write(json.dumps(req2) + "\n")
        proc.stdin.flush()

        line2 = frames.get(timeout=60)
        assert line2.endswith("\n")
        resp2 = json.loads(line2)
        assert resp2["jsonrpc"] == "2.0"
        assert resp2["id"] == 2
        tool_names = [t["name"] for t in resp2["result"]["tools"]]
        assert "migration_doctor" in tool_names
        assert "migration_inventory" in tool_names

        # Request 3: doctor tool call
        req3 = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "migration_doctor", "arguments": {}},
        }
        proc.stdin.write(json.dumps(req3) + "\n")
        proc.stdin.flush()

        line3 = frames.get(timeout=60)
        assert line3.endswith("\n")
        resp3 = json.loads(line3)
        assert resp3["jsonrpc"] == "2.0"
        assert resp3["id"] == 3
        assert not resp3["result"].get("isError", False)

    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            pytest.fail("MCP server did not exit after stdin EOF")
        finally:
            for reader in readers:
                reader.join(timeout=5)
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

    # Acceptance: Every stdout byte is valid JSON-RPC frame (lines of pure JSON)
    for line in stdout_lines:
        if line.strip():
            frame = json.loads(line)
            assert "jsonrpc" in frame

    # Verification: Secrets NEVER appear in stdout or stderr
    assert secret_token not in "".join(stdout_lines)
    assert secret_token not in "".join(stderr_lines)
    assert proc.returncode == 0


@pytest.mark.anyio
async def test_transport_redacts_both_result_views_and_sdk_validation(plan_fixture) -> None:
    binding, plan_id, store = plan_fixture
    token = "sk-offline-contract-fixture-123456789"
    plan = store.get_plan(plan_id)
    assert plan is not None
    store.save_plan(
        plan.model_copy(update={"steps": [plan.steps[0].model_copy(update={"description": token})]})
    )
    async with create_connected_session(binding, store.state_dir) as (session, tg):
        await session.initialize()
        result = await session.call_tool(
            "migration_plan_show", {"project_id": binding.project_id, "plan_id": plan_id}
        )
        assert not result.is_error
        assert token not in result.model_dump_json()
        assert "[REDACTED]" in result.model_dump_json()
        rejected = await session.call_tool("migration_inventory", {"file_offset": token})
        assert rejected.is_error and token not in rejected.model_dump_json()
        oversized = await session.call_tool("migration_inventory", {"project_id": "x" * 70_000})
        assert oversized.is_error and len(oversized.model_dump_json()) < 1024
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_transport_enforces_capability_and_assurance(plan_fixture) -> None:
    binding, plan_id, store = plan_fixture
    public = InspectionContext(
        actor="contract-local-user",
        assurance=AssuranceLevel.MODE_C,
        capabilities=frozenset(InspectionCapability),
    )
    async with create_connected_session(binding, store.state_dir, public) as (session, tg):
        await session.initialize()
        assert not (await session.call_tool("migration_doctor", {})).is_error
        denied = await session.call_tool(
            "migration_plan_show", {"project_id": binding.project_id, "plan_id": plan_id}
        )
        assert denied.is_error and "ASSURANCE_REQUIRED" in denied.model_dump_json()
        tg.cancel_scope.cancel()
    no_grants = public.model_copy(update={"capabilities": frozenset()})
    async with create_connected_session(binding, store.state_dir, no_grants) as (session, tg):
        await session.initialize()
        denied = await session.call_tool("migration_doctor", {})
        assert denied.is_error and "CAPABILITY_DENIED" in denied.model_dump_json()
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_transport_rejects_foreign_plan_without_disclosing_it(
    plan_fixture, tmp_path: Path
) -> None:
    binding, plan_id, store = plan_fixture
    plan = store.get_plan(plan_id)
    assert plan is not None
    foreign = tmp_path / "foreign-root-private"
    foreign.mkdir()
    store.save_plan(plan.model_copy(update={"source_root": str(foreign)}))
    async with create_connected_session(binding, store.state_dir) as (session, tg):
        await session.initialize()
        result = await session.call_tool(
            "migration_plan_show", {"project_id": binding.project_id, "plan_id": plan_id}
        )
        assert result.is_error and "PROJECT_MISMATCH" in result.model_dump_json()
        assert foreign.name not in result.model_dump_json()
        tg.cancel_scope.cancel()


def test_cli_import_does_not_load_model_sdks() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import migration_agent.cli; "
            "assert 'agents' not in sys.modules; assert 'google.genai' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_subprocess_startup_failure_keeps_stdout_empty() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "migration_agent.cli",
            "mcp",
            "serve",
            "--project-root",
            str(FIXTURE_PATH),
            "--state-dir",
            str(FIXTURE_PATH),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "UNSAFE_ROOT_OVERLAP" in result.stderr
    assert not (FIXTURE_PATH / "checkpoints.db").exists()


@pytest.mark.anyio
async def test_host_analysis_proposal_over_transport_is_idempotent(tmp_path: Path) -> None:
    from migration_agent.adapters.mcp.tools import _create_default_framework_registry
    from migration_agent.adapters.project_evidence import LocalProjectEvidence

    root = tmp_path / "repo"
    shutil.copytree(FIXTURE_PATH, root)
    for args in [
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Fixture",
        ),
    ]:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    binding = ProjectBinding(root)
    evidence = LocalProjectEvidence(root, _create_default_framework_registry())
    base = evidence.repository_state()
    path = "app/components/user-card.js"
    payload = {
        "base_revision": base.revision,
        "worktree_fingerprint": base.fingerprint,
        "summary": "Grounded analysis",
        "findings": [
            {
                "id": "finding-1",
                "title": "Component",
                "category": "component",
                "severity": "low",
                "confidence": 1,
                "description": "Migrate the component",
                "evidence_references": [{"path": path, "description": "Source"}],
            }
        ],
        "citations": [
            {"path": path, "sha256": hashlib.sha256(evidence.read_text(path).encode()).hexdigest()}
        ],
    }
    from security_project import security_project

    authorization, _, _ = security_project(tmp_path / "security", root)
    async with create_connected_session(
        binding, authorization.state, settings=authorization.settings
    ) as (session, tg):
        await session.initialize()
        request = {
            "project_id": binding.project_id,
            "request_id": "analysis-1",
            "analysis_payload": payload,
        }
        first = await session.call_tool("migration_submit_analysis", request)
        second = await session.call_tool("migration_submit_analysis", request)
        assert not first.is_error and first.structured_content == second.structured_content
        assert first.structured_content and first.structured_content["status"] == "SUCCEEDED"
        status = await session.call_tool(
            "migration_operation_status",
            {
                "project_id": binding.project_id,
                "operation_id": first.structured_content["operation_id"],
            },
        )
        assert not status.is_error and status.structured_content
        assert status.structured_content["repository"]["clean"]
        tg.cancel_scope.cancel()
    assert not (root / ".agent").exists()
