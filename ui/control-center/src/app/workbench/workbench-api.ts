import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { catchError, map, throwError, timeout } from 'rxjs';
import { ApiError, apiError } from '../core/api/api-error';
import type {
  Health,
  ImageContent,
  NodePage,
  Receipt,
  Session,
  WorkAnswer,
  WorkCommand,
  WorkDetail,
  WorkEvents,
  WorkFileDiff,
  WorkQuestion,
} from './workbench.models';

interface Envelope<T> {
  readonly status: 'ok' | 'error';
  readonly data?: T;
}
export interface TreeQuery {
  readonly project: string;
  readonly parent?: string;
  readonly query?: string;
  readonly offset?: string;
  readonly attention?: string;
  readonly kind?: string;
}

@Injectable({ providedIn: 'root' })
export class WorkbenchApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/workbench';

  session(): Observable<Session> {
    return this.read('/api/v1/session');
  }
  tree(params: TreeQuery): Observable<NodePage> {
    return this.read(this.base + '/tree', { ...params });
  }
  detail(project: string, node: string, revision: string): Observable<WorkDetail> {
    return this.read(this.base + '/detail', { project, node, revision });
  }
  events(project: string, cursor: number, revision: string): Observable<WorkEvents> {
    return this.read(this.base + '/events', { project, cursor: String(cursor), revision });
  }
  image(project: string, node: string, revision: string, index: number): Observable<ImageContent> {
    return this.read(this.base + '/image', { project, node, revision, index: String(index) });
  }
  fileDiff(detail: WorkDetail, index: number): Observable<WorkFileDiff> {
    return this.read(this.base + '/diff', {
      project: detail.project_id,
      node: detail.node.node_id,
      revision: detail.revision,
      artifact: detail.changeset_digest ?? '',
      index: String(index),
    });
  }
  health(): Observable<Health> {
    return this.read('/api/v1/health');
  }
  command(command: WorkCommand): Observable<Receipt> {
    return this.http.post<Envelope<Receipt>>(this.base + '/command', command).pipe(this.unwrap());
  }
  answer(question: WorkQuestion): Observable<WorkAnswer> {
    return this.http
      .post<Envelope<WorkAnswer>>(this.base + '/answer', question)
      .pipe(this.unwrap());
  }

  private read<T>(url: string, params: Record<string, string> = {}): Observable<T> {
    return this.http.get<Envelope<T>>(url, { params }).pipe(this.unwrap());
  }
  private unwrap<T>(): (source: Observable<Envelope<T>>) => Observable<T> {
    return (source) =>
      source.pipe(
        timeout({ first: 15000 }),
        map((response) => {
          if (response.status !== 'ok' || response.data === undefined || response.data === null)
            throw new ApiError('server', 'The service returned an incompatible response.');
          return response.data;
        }),
        catchError((error) => throwError(() => apiError(error))),
      );
  }
}
