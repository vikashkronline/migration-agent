import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, finalize, fromEvent, map, switchMap, tap } from 'rxjs';
import { ApiError, apiError } from '../../../core/api/api-error';
import { CodeLine } from '../../../shared/code-line/code-line';
import { Feedback } from '../../../shared/feedback/feedback';
import { WorkbenchApi } from '../../workbench-api';
import type { DiffLine, WorkDetail, WorkFileDiff } from '../../workbench.models';

export interface SplitRow {
  readonly old: DiffLine | null;
  readonly next: DiffLine | null;
}
export function splitLines(lines: readonly DiffLine[]): readonly SplitRow[] {
  const rows: SplitRow[] = [];
  let removed: DiffLine[] = [],
    added: DiffLine[] = [];
  const flush = (): void => {
    for (let i = 0; i < Math.max(removed.length, added.length); i++)
      rows.push({ old: removed[i] ?? null, next: added[i] ?? null });
    removed = [];
    added = [];
  };
  for (const line of lines) {
    if (line.kind === 'context') {
      flush();
      rows.push({ old: line, next: line });
    } else if (line.kind === 'remove') removed.push(line);
    else added.push(line);
  }
  flush();
  return rows;
}

@Component({
  selector: 'cc-diff-viewer',
  imports: [Feedback, CodeLine],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './diff-viewer.html',
  styleUrl: './diff-viewer.css',
})
export class DiffViewer {
  readonly detail = input.required<WorkDetail>();
  private readonly api = inject(WorkbenchApi);
  private readonly media = inject(DOCUMENT).defaultView?.matchMedia?.('(max-width:767px)');
  protected readonly compact = toSignal(
    this.media
      ? fromEvent<MediaQueryListEvent>(this.media, 'change').pipe(map((event) => event.matches))
      : EMPTY,
    { initialValue: this.media?.matches ?? true },
  );
  protected readonly mode = signal<'unified' | 'split'>('unified');
  protected readonly split = computed(() => !this.compact() && this.mode() === 'split');
  protected readonly showLineEndings = signal(false);
  protected readonly index = linkedSignal(() => {
    this.detail();
    return 0;
  });
  protected readonly search = signal('');
  protected readonly files = computed(() =>
    this.detail()
      .files.map((path, index) => ({ path, index }))
      .filter((file) => file.path.toLowerCase().includes(this.search().toLowerCase())),
  );
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly content = signal<WorkFileDiff | null>(null);
  private readonly reload = signal(0);
  protected readonly hunks = computed(
    () => this.content()?.hunks.map((hunk) => ({ ...hunk, rows: splitLines(hunk.lines) })) ?? [],
  );
  constructor() {
    toObservable(
      computed(() => ({ detail: this.detail(), index: this.index(), attempt: this.reload() })),
    )
      .pipe(
        switchMap(({ detail, index }) => {
          this.content.set(null);
          this.error.set('');
          if (!detail.changeset_digest || !detail.files.length) return EMPTY;
          this.loading.set(true);
          return this.api.fileDiff(detail, index).pipe(
            tap((diff) => {
              if (
                diff.project_id !== detail.project_id ||
                diff.node_id !== detail.node.node_id ||
                diff.revision !== detail.revision ||
                diff.changeset_digest !== detail.changeset_digest ||
                diff.path !== detail.files[index] ||
                diff.base_revision !== detail.base_revision
              )
                throw new ApiError(
                  'stale',
                  'The diff does not match the selected artifact. Open the current item.',
                );
              this.content.set(diff);
            }),
            catchError((error) => {
              this.error.set(apiError(error).message);
              return EMPTY;
            }),
            finalize(() => this.loading.set(false)),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();
  }
  protected retry(): void {
    this.reload.update((value) => value + 1);
  }
}
