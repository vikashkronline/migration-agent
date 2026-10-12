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
import { CcIcon } from '../../../shared/icon/cc-icon';
import { Feedback } from '../../../shared/feedback/feedback';
import { WorkbenchApi } from '../../workbench-api';
import type { WorkAnswer, WorkDetail } from '../../workbench.models';
import { WorkbenchStore } from '../../workbench-store';

@Component({
  selector: 'cc-ask-page',
  imports: [Feedback, CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './ask-page.html',
})
export class AskPage {
  protected readonly store = inject(WorkbenchStore);
  private readonly api = inject(WorkbenchApi);
  private readonly requests = new Subject<{ detail: WorkDetail; question: string }>();
  protected readonly question = linkedSignal(() => {
    this.store.selection();
    return '';
  });
  protected readonly busy = signal(false);
  protected readonly error = linkedSignal(() => {
    this.store.detail();
    return '';
  });
  protected readonly answer = linkedSignal<WorkAnswer | null>(() => {
    this.store.detail();
    return null;
  });
  protected readonly valid = computed(
    () =>
      this.question().trim().length >= 3 &&
      this.question().length <= 2048 &&
      this.store.fresh() &&
      !this.busy(),
  );
  protected readonly terminalArguments = computed(() => {
    const command = this.store.detail()?.ask_command ?? [];
    return JSON.stringify(
      command.length ? [...command.slice(0, 2), this.question().trim(), ...command.slice(2)] : [],
      null,
      2,
    );
  });

  constructor() {
    const context = toObservable(this.store.detail);
    this.requests
      .pipe(
        switchMap(({ detail, question }) => {
          this.busy.set(true);
          this.error.set('');
          return this.api
            .answer({
              project_id: detail.project_id,
              node_id: detail.node.node_id,
              revision: detail.revision,
              question,
            })
            .pipe(
              tap((res) => {
                this.answer.set(res);
              }),
              catchError((err) => {
                this.error.set(apiError(err).message);
                return EMPTY;
              }),
              finalize(() => {
                this.busy.set(false);
              }),
              takeUntil(
                context.pipe(
                  filter(
                    (next) =>
                      next === null ||
                      next.project_id !== detail.project_id ||
                      next.node.node_id !== detail.node.node_id ||
                      next.revision !== detail.revision,
                  ),
                ),
              ),
            );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();
  }

  protected ask(event: Event): void {
    event.preventDefault();
    const detail = this.store.detail();
    if (!this.valid() || !detail) {
      return;
    }
    this.requests.next({ detail, question: this.question().trim() });
  }
}
