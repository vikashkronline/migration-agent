import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  linkedSignal,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { EMPTY, Subject, catchError, filter, finalize, switchMap, takeUntil, tap } from 'rxjs';
import { apiError } from '../../../core/api/api-error';
import { Feedback } from '../../../shared/feedback/feedback';
import { WorkbenchApi } from '../../workbench-api';
import type { WorkDetail } from '../../workbench.models';
import { WorkbenchStore } from '../../workbench-store';
import { DiffViewer } from './diff-viewer';

@Component({
  selector: 'cc-artifacts-page',
  imports: [Feedback, DiffViewer],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './artifacts-page.html',
})
export class ArtifactsPage {
  protected readonly store = inject(WorkbenchStore);
  private readonly api = inject(WorkbenchApi);
  private readonly requests = new Subject<{ detail: WorkDetail; index: number }>();
  protected readonly loading = signal(false);
  protected readonly error = linkedSignal(() => {
    this.store.detail();
    return '';
  });
  private readonly content = linkedSignal<{ detail: WorkDetail; url: string } | null>(() => {
    this.store.detail();
    return null;
  });
  protected readonly image = computed(() =>
    this.content()?.detail === this.store.detail() ? (this.content()?.url ?? '') : '',
  );

  constructor() {
    const context = toObservable(this.store.detail);
    this.requests
      .pipe(
        switchMap(({ detail, index }) => {
          this.loading.set(true);
          this.error.set('');
          this.content.set(null);
          return this.api
            .image(detail.project_id, detail.node.node_id, detail.revision, index)
            .pipe(
              takeUntil(context.pipe(filter((current) => current !== detail))),
              tap((image) => {
                if (image.mime_type !== 'image/png') throw new Error('Unsupported evidence format');
                if (this.store.detail() === detail)
                  this.content.set({ detail, url: 'data:image/png;base64,' + image.data });
              }),
              catchError((error) => {
                if (this.store.detail() === detail) this.error.set(apiError(error).message);
                return EMPTY;
              }),
              finalize(() => this.loading.set(false)),
            );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();
  }
  protected showImage(index: number): void {
    const detail = this.store.detail();
    if (detail) this.requests.next({ detail, index });
  }
}
