import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'cc-feedback',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '<section class="alert" [class.alert-warning]="tone() === \'warning\'" [class.alert-info]="tone() === \'info\'" [attr.role]="tone() === \'warning\' ? \'alert\' : \'status\'"><h2 class="h6">{{ title() }}</h2><p class="mb-2">{{ message() }}</p>@if (retryLabel()) {<button class="btn btn-sm btn-outline-secondary" (click)="retry.emit()">{{ retryLabel() }}</button>}</section>',
})
export class Feedback {
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  readonly tone = input<'warning' | 'info'>('warning');
  readonly retryLabel = input('');
  readonly retry = output<void>();
}
