"""Crash reconciliation never resumes an uncertain source mutation automatically."""

import uuid

from migration_agent.domain.host_workflow import Lifecycle, OperationStatus
from migration_agent.ports.checkpoints import CheckpointPort
from migration_agent.ports.host_workflow import RecoveryProbePort, WorkflowStorePort


def reconcile_workflows(
    project_id: str, store: WorkflowStorePort, checkpoints: CheckpointPort, probe: RecoveryProbePort
) -> None:
    try:
        lease = store.acquire_lease(project_id, f"reconcile-{uuid.uuid4().hex}")
    except ValueError as error:
        if str(error).startswith("WRITER_BUSY"):
            return
        raise
    try:
        for record in store.list_workflows(project_id):
            if record.state == Lifecycle.APPLY_INTENT:
                changeset = checkpoints.get_changeset(record.changeset_id or "")
                outcome = probe.classify(record, changeset) if changeset else "ambiguous"
                state = (
                    Lifecycle.APPLY_COMPLETED
                    if outcome == "target"
                    else Lifecycle.RECOVERY_REQUIRED
                )
                store.save_workflow(
                    record.model_copy(
                        update={
                            "state": state,
                            "approval_nonce": None,
                            "recovery_note": f"Interrupted apply: disk classification={outcome}",
                        }
                    ),
                    lease,
                )
            elif record.state == Lifecycle.VALIDATION_RUNNING:
                store.save_workflow(
                    record.model_copy(
                        update={
                            "state": Lifecycle.VALIDATION_FAILED,
                            "validation_results": (),
                            "validation_digest": None,
                            "recovery_note": "Interrupted validation must run again.",
                        }
                    ),
                    lease,
                )
            elif record.state == Lifecycle.REPAIRING:
                store.save_workflow(
                    record.model_copy(
                        update={
                            "state": Lifecycle.BASE_CHANGED,
                            "recovery_note": "Interrupted repair requires a fresh inspected plan.",
                        }
                    ),
                    lease,
                )
        for operation in store.list_active_operations(project_id):
            status = (
                OperationStatus.CANCELLED
                if operation.status == OperationStatus.CANCEL_REQUESTED
                else OperationStatus.FAILED
            )
            if operation.kind == "apply":
                status = OperationStatus.RECOVERY_REQUIRED
            store.save_operation(
                operation.model_copy(
                    update={
                        "status": status,
                        "message": "Interrupted operation reconciled; inspect before retrying.",
                    }
                ),
                lease,
            )
    finally:
        store.release_lease(lease)
