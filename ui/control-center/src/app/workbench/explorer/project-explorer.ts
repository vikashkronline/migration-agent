import { ChangeDetectionStrategy, Component, inject, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CcIcon, type IconName } from '../../shared/icon/cc-icon';
import { StatusBadge } from '../../shared/status-badge/status-badge';
import { WorkbenchStore } from '../workbench-store';
import type { WorkNode } from '../workbench.models';

@Component({
  selector: 'cc-project-explorer',
  imports: [RouterLink, StatusBadge, CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './project-explorer.html',
})
export class ProjectExplorer {
  readonly selected = output<void>();
  protected readonly store = inject(WorkbenchStore);

  protected getNodeIcon(node: WorkNode): IconName {
    if (node.kind === 'project') return 'folder2';
    if (node.node_id === 'foundation') return 'shield-check';
    if (node.node_id === 'work') return 'diagram-3';
    if (node.node_id === 'knowledge') return 'journal-bookmark';
    if (node.kind === 'reference') return 'file-earmark-text';
    if (node.kind === 'task') {
      if (node.status === 'APPLY_COMPLETED') return 'check-circle-fill';
      if (node.status === 'VALIDATION_FAILED' || node.status === 'RECOVERY_REQUIRED') {
        return 'exclamation-triangle-fill';
      }
      if (node.status === 'STAGE_VERIFIED' || node.status === 'VALIDATION_PASSED') {
        return 'patch-check-fill';
      }
      if (node.status === 'APPROVAL_RECORDED' || node.status === 'READY_TO_APPLY') {
        return 'lock';
      }
      return 'hourglass-split';
    }
    if (node.kind === 'group') return 'collection';
    return 'folder2';
  }
}
