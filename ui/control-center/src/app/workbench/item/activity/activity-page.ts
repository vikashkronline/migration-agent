import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { WorkbenchStore } from '../../workbench-store';

@Component({
  selector: 'cc-activity-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '@if (store.detail(); as detail) {<h2 class="h6">Durable operations</h2><ol class="list-unstyled">@for (operation of detail.activity; track $index) {<li class="card mb-3"><div class="card-body"><h3 class="h6">{{operation[0]}}</h3><pre class="small mb-0">{{operation[1]}}</pre></div></li>} @empty {<li>No operation diagnostics recorded.</li>}</ol><p class="small text-body-secondary">Latest bounded operation diagnostics for this exact task. A queued request is not a completed operation.</p>}',
})
export class ActivityPage {
  protected readonly store = inject(WorkbenchStore);
}
