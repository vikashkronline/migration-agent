"""Opt-in offline acceptance with installed Angular tools; no fixture tool stand-ins."""

import ctypes
import os
import shutil
import sys
from pathlib import Path

import pytest
from test_destination_workflow import separate
from test_shared_apply import HumanFixture
from test_shared_apply import workflow as workflow

from migration_agent.adapters.fenced_validation import validation_commands
from migration_agent.adapters.foundation_transformation import FoundationTransformationAdapter
from migration_agent.adapters.validation_backend import ValidationBackend
from migration_agent.domain.host_workflow import Lifecycle
from migration_agent.domain.redaction import RedactionPolicy


@pytest.mark.skipif(
    os.environ.get("AGENT_TEST_REAL_ANGULAR") != "1",
    reason="Opt-in offline installed Angular acceptance",
)
def test_generated_foundation_and_component_pass_real_native_checks(workflow, tmp_path):
    if sys.platform == "win32" and ctypes.WinDLL("shell32").IsUserAnAdmin():
        pytest.skip("Native validation requires a non-elevated account.")
    if sys.platform == "linux" and os.geteuid() == 0:
        pytest.skip("Native validation requires a non-root account.")
    node = shutil.which("node")
    modules = Path("ui/control-center/node_modules").resolve()
    if not node or not modules.is_dir():
        pytest.skip("Installed offline Node/Angular dependencies required.")
    target = separate(workflow, tmp_path)
    runtime, plan_id, _ = workflow
    provisioned = os.environ.get("AGENT_TEST_ANGULAR_TOOLCHAIN")
    tools = Path(provisioned) if provisioned else tmp_path / "installed-tools"
    if not provisioned:
        tools.mkdir()
        # Trusted test provisioning only: application files still come exclusively from stage().
        tool_node = tools / ("node.exe" if os.name == "nt" else "bin/node")
        tool_node.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(node, tool_node)
        tool_node.chmod(0o755)

        def excluded(directory, names):
            return [
                name for name in names if RedactionPolicy.is_sensitive_path(Path(directory) / name)
            ]

        shutil.copytree(modules, tools / "node_modules", copy_function=os.link, ignore=excluded)
        npm = Path(node).parent / "node_modules/npm"
        if not npm.is_dir():
            pytest.skip("Installed npm required for native fixed templates.")
        shutil.copytree(npm, tools / "node_modules/npm", copy_function=os.link, ignore=excluded)
    settings = runtime.settings.model_copy(
        update={
            "validation_mode": "native",
            "validation_catalog": "node-angular-v21",
            "native_toolchain_root": tools,
            "native_dependencies_root": tools / "node_modules",
        }
    )
    runtime.runner = ValidationBackend(
        settings, runtime.proposals, runtime.store, runtime.staging, runtime.state, runtime.trust
    )
    runtime.apply_service.execution_gate = runtime.runner
    runtime.apply_service.browser_gate = None
    runtime.apply_service.foundation_contract = lambda: "fixture-architecture-contract"
    runtime.apply_service.transformation.foundation_adapter = FoundationTransformationAdapter()
    original = runtime.store.get_plan(plan_id)
    foundation = original.steps[0].model_copy(
        update={"step_id": "foundation", "scope": "foundation", "dependencies": []}
    )
    component = original.steps[0].model_copy(update={"dependencies": ["foundation"]})
    plan = original.model_copy(
        update={
            "plan_id": "real-angular-plan",
            "run_id": "real-angular",
            "steps": [foundation, component],
        }
    )
    runtime.store.save_plan(plan)
    commands = tuple(c for group in validation_commands("node-angular-v21").values() for c in group)
    before = runtime.proposals.evidence.repository_state()
    for step in plan.steps:
        lease = runtime.store.acquire_lease(runtime.binding.project_id, step.step_id, ttl=900)
        try:
            staged = runtime.apply_service.stage(plan.plan_id, step.step_id, lease)
            consent = runtime.runner.consent_request(
                staged, commands, 0, lambda lease=lease: runtime.store.renew_lease(lease, 900)
            )
            consent = consent.model_copy(update={"signature": runtime.runner.proof.sign(consent)})
            runtime.store.save_native_consent(consent, lease)
            checked = runtime.apply_service.validate(
                plan.plan_id, step.step_id, commands, runtime.runner, lease
            )
            assert checked.state == Lifecycle.VALIDATION_PASSED, checked.validation_results
        finally:
            runtime.store.release_lease(lease)
        runtime.apply_service.approve(plan.plan_id, step.step_id, HumanFixture())
        runtime.apply_service.apply(plan.plan_id, step.step_id, staged.changeset_id)
    assert (target / "src/app/app.component.ts").is_file()
    assert runtime.proposals.evidence.repository_state() == before
