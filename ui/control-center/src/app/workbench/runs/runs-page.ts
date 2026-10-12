import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError, distinctUntilChanged, filter, finalize, switchMap, tap } from 'rxjs';
import { apiError } from '../../core/api/api-error';
import { CcIcon } from '../../shared/icon/cc-icon';
import { Feedback } from '../../shared/feedback/feedback';
import { StatusBadge } from '../../shared/status-badge/status-badge';
import { WorkbenchApi } from '../workbench-api';
import type { WorkNode } from '../workbench.models';
import { WorkbenchStore } from '../workbench-store';

@Component({
  selector: 'cc-runs-page',
  imports: [RouterLink, Feedback, StatusBadge, CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './runs-page.html',
})
export class RunsPage {
  protected readonly store = inject(WorkbenchStore);
  private readonly api = inject(WorkbenchApi);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly items = signal<readonly WorkNode[]>([]);
  protected readonly total = signal(0);
  protected readonly next = signal<number | null>(0);
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  constructor() {
    toObservable(this.store.snapshotRevision)
      .pipe(
        filter(Boolean),
        distinctUntilChanged(),
        tap(() => {
          this.items.set([]);
          this.next.set(0);
        }),
        switchMap(() => this.read(0)),
        takeUntilDestroyed(),
      )
      .subscribe();
  }
  protected more(): void {
    const offset = this.next();
    if (offset !== null && !this.loading())
      this.read(offset).pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
  }
  protected retry(): void {
    this.items.set([]);
    this.read(0).pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
  }
  private read(offset: number) {
    const revision = this.store.snapshotRevision();
    this.loading.set(true);
    this.error.set('');
    return this.api
      .tree({ project: this.store.session()!.project_id, kind: 'task', offset: String(offset) })
      .pipe(
        tap((page) => {
          if (revision !== this.store.snapshotRevision() || page.revision !== revision) {
            this.store.refresh();
            return;
          }
          this.items.update((prev) => [...prev, ...page.nodes]);
          this.total.set(page.total);
          this.next.set(page.next_offset);
        }),
        catchError((err) => {
          this.error.set(apiError(err).message);
          return EMPTY;
        }),
        finalize(() => {
          this.loading.set(false);
        }),
      );
  }
}
