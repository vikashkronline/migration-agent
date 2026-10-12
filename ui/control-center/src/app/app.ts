import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ApplicationErrors } from './core/errors/application-errors';
import { Feedback } from './shared/feedback/feedback';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, Feedback],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '@if (errors.failed()) {<main class="container py-5"><h1 class="h3">Control Center interrupted</h1><cc-feedback title="Unexpected interface error" message="Reload to recover the interface. Existing execution may still be running; inspect durable activity before requesting another action." retryLabel="Reload interface" (retry)="reload()" /></main>} @else {<router-outlet />}',
})
export class App {
  protected readonly errors = inject(ApplicationErrors);
  private readonly document = inject(DOCUMENT);
  protected reload(): void {
    this.document.defaultView?.location.reload();
  }
}
