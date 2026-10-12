import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal } from '@angular/core';
import { CcIcon, type IconName } from '../../shared/icon/cc-icon';
import { ModalDialog } from '../../shared/modal-dialog/modal-dialog';
import type { WorkAction, WorkDetail } from '../workbench.models';
import { WorkbenchStore } from '../workbench-store';

interface Confirmation {
  readonly detail: WorkDetail;
  readonly action: WorkAction;
}
@Component({
  selector: 'cc-workflow-actions',
  imports: [ModalDialog, CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './workflow-actions.html',
})
export class WorkflowActions {
  protected readonly store = inject(WorkbenchStore);
  protected readonly confirmation = linkedSignal<Confirmation | null>(() => {
    this.store.detail();
    this.store.fresh();
    return null;
  });
  protected readonly enabled = computed(
    () =>
      this.store.fresh() && !this.store.pending() && this.store.command()?.outcome !== 'unknown',
  );
  protected confirm(action: WorkAction): void {
    const detail = this.store.detail();
    if (detail && action.available && this.enabled()) this.confirmation.set({ detail, action });
  }
  protected execute(): void {
    const draft = this.confirmation();
    this.confirmation.set(null);
    if (draft) this.store.requestAction(draft.detail, draft.action.kind);
  }

  protected getActionIcon(kind: string): IconName {
    if (kind === 'stage') return 'hammer';
    if (kind === 'validate') return 'clipboard-check';
    if (kind === 'apply') return 'patch-check-fill';
    return 'hammer';
  }
}
