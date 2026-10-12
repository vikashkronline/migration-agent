import { JsonPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError, finalize, tap } from 'rxjs';
import { apiError } from '../../core/api/api-error';
import { Feedback } from '../../shared/feedback/feedback';
import { WorkbenchApi } from '../workbench-api';
import type { Health } from '../workbench.models';
import { WorkbenchStore } from '../workbench-store';

@Component({
  selector: 'cc-health-page',
  imports: [JsonPipe, RouterLink, Feedback],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '<h1 id="content-heading" class="h3" tabindex="-1">Platform health</h1><p>These diagnostics concern the platform, not project readiness.</p><a class="btn btn-sm btn-outline-secondary mb-3" [routerLink]="[\'../items\', store.selection().nodeId]">Return to selected item</a>@if (error()) {<cc-feedback title="Diagnostics unavailable" [message]="error()" retryLabel="Retry diagnostics" (retry)="retry()" />}@if (loading()) {<p role="status">Loading diagnostics…</p>}@if (health(); as health) {<ul class="list-unstyled">@for (check of health.checks; track check.name) {<li class="card mb-3"><div class="card-body"><h2 class="h6">{{check.name}} · {{check.status}}</h2><pre class="small mb-0">{{check.details | json}}</pre></div></li>}</ul>}<p class="small text-body-secondary">Native execution requires separate human consent. Process supervision is not filesystem isolation.</p>',
})
export class HealthPage {
  protected readonly store = inject(WorkbenchStore);
  private readonly api = inject(WorkbenchApi);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly health = signal<Health | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  constructor() {
    this.retry();
  }
  protected retry(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set('');
    this.api
      .health()
      .pipe(
        tap((health) => this.health.set(health)),
        catchError((error) => {
          this.error.set(apiError(error).message);
          return EMPTY;
        }),
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
}
