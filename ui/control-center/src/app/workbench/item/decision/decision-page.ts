import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { WorkbenchStore } from '../../workbench-store';

@Component({
  selector: 'cc-decision-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './decision-page.html',
})
export class DecisionPage {
  protected readonly store = inject(WorkbenchStore);
  protected readonly reviewArguments = computed(() =>
    JSON.stringify(this.store.detail()?.review_command ?? [], null, 2),
  );
}
