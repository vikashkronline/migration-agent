import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { catchError, map, throwError, timeout } from 'rxjs';
import { apiError } from '../../core/api/api-error';
import type {
  AccessDecision,
  AccessMutation,
  AccessPolicy,
  AccessReview,
  DirectoryRequest,
  DirectoryResult,
  OnboardingPacket,
} from './access.models';

@Injectable({ providedIn: 'root' })
export class AccessApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/access';
  session(): Observable<AccessDecision> {
    return this.unwrap(this.http.get(this.base + '/session'));
  }
  policy(): Observable<AccessPolicy> {
    return this.unwrap(this.http.get(this.base));
  }
  catalog(): Observable<readonly string[]> {
    return this.unwrap(this.http.get(this.base + '/capabilities'));
  }
  propose(base_digest: string, mutations: readonly AccessMutation[]): Observable<AccessReview> {
    return this.unwrap(this.http.post(this.base + '/proposals', { base_digest, mutations }));
  }
  directory(request: DirectoryRequest): Observable<DirectoryResult> {
    return this.unwrap(this.http.post(this.base + '/git-members', request), 25000);
  }
  repositoryPreview(request: DirectoryRequest): Observable<DirectoryResult> {
    return this.unwrap(this.http.post(this.base + '/repository-preview', request), 25000);
  }
  importMembers(
    base_digest: string,
    directory: DirectoryRequest,
    account_ids: readonly string[],
    roles: readonly string[],
  ): Observable<AccessReview> {
    return this.unwrap(
      this.http.post(this.base + '/git-import', { base_digest, directory, account_ids, roles }),
      25000,
    );
  }
  review(id: string): Observable<AccessReview> {
    return this.unwrap(this.http.get(this.base + '/proposal', { params: { id } }));
  }
  onboarding(principal: string): Observable<OnboardingPacket> {
    return this.unwrap(this.http.get(this.base + '/onboarding', { params: { principal } }));
  }
  private unwrap<T>(source: Observable<unknown>, deadline = 15000): Observable<T> {
    return source.pipe(
      timeout({ first: deadline }),
      map((value) => {
        const envelope = value as { status?: string; data?: T };
        if (envelope.status !== 'ok' || envelope.data === undefined)
          throw new Error('Incompatible access response');
        return envelope.data;
      }),
      catchError((error: unknown) => throwError(() => apiError(error))),
    );
  }
}
