import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { WorkbenchStore } from '../../workbench-store';

@Component({
  selector: 'cc-steps-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '@if (store.detail(); as detail) {<h2 class="h6">Recorded workflow milestones</h2><ol class="list-unstyled d-flex flex-wrap gap-3">@for (milestone of detail.milestones; track $index) {<li class="card"><div class="card-body"><strong>{{milestone[0]}}</strong><span class="d-block text-break mt-1">{{milestone[1]}}</span></div></li>} @empty {<li>No workflow milestones are recorded for this selection. Open its child tasks for their current workflow evidence.</li>}</ol><p class="small text-body-secondary">Recorded, validated, approved and verified complete are separate states. Historical evidence never grants current execution authority.</p>}',
})
export class StepsPage {
  protected readonly store = inject(WorkbenchStore);
}
