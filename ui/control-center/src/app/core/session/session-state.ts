import { Injectable, inject, signal } from '@angular/core';
import type { Observable } from 'rxjs';
import { catchError, shareReplay, tap, throwError } from 'rxjs';
import { WorkbenchApi } from '../../workbench/workbench-api';
import type { Session } from '../../workbench/workbench.models';

@Injectable({ providedIn: 'root' })
export class SessionState {
  private readonly api = inject(WorkbenchApi);
  private readonly value = signal<Session | null>(null);
  readonly session = this.value.asReadonly();
  private request: Observable<Session> | null = null;
  private receivedAt = 0;

  ensure(): Observable<Session> {
    if (this.receivedAt && Date.now() - this.receivedAt >= 15000) this.request = null;
    this.request ??= this.api.session().pipe(
      tap((session) => {
        this.receivedAt = Date.now();
        this.value.set(session);
      }),
      catchError((error: unknown) => {
        this.request = null;
        this.value.set(null);
        return throwError(() => error);
      }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    return this.request;
  }
  reset(): void {
    this.request = null;
    this.value.set(null);
  }
  require(): Session {
    const session = this.value();
    if (!session) throw new Error('Session is not initialized');
    return session;
  }
}
