import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { catchError, map, throwError, timeout } from 'rxjs';
import { ApiError, apiError } from '../../core/api/api-error';
import type {
  ConfigurationCheck,
  ConfigurationProposal,
  ConfigurationReceipt,
  ConfigurationReview,
  ConfigurationView,
  LocalConfiguration,
  ProjectConfiguration,
  SetupPlan,
  SetupRequest,
} from './settings.models';

interface Envelope<T> {
  readonly status: 'ok' | 'error';
  readonly data?: T;
}
@Injectable({ providedIn: 'root' })
export class SettingsApi {
  private readonly http = inject(HttpClient);
  private base(project: string): string {
    return '/api/v1/projects/' + encodeURIComponent(project) + '/configuration';
  }
  view(project: string): Observable<ConfigurationView> {
    return this.unwrap(this.http.get<Envelope<ConfigurationView>>(this.base(project)));
  }
  local(
    project: string,
    expected_revision: string,
    request_id: string,
    configuration: LocalConfiguration,
  ): Observable<ConfigurationReceipt> {
    return this.unwrap(
      this.http.post<Envelope<ConfigurationReceipt>>(this.base(project) + '/local', {
        expected_revision,
        request_id,
        configuration,
      }),
    );
  }
  propose(
    project: string,
    expected_revision: string,
    request_id: string,
    configuration: ProjectConfiguration,
  ): Observable<ConfigurationReceipt> {
    return this.unwrap(
      this.http.post<Envelope<ConfigurationReceipt>>(this.base(project) + '/proposals', {
        expected_revision,
        request_id,
        configuration,
      }),
    );
  }
  review(project: string, proposal: string, prepare: boolean): Observable<ConfigurationReview> {
    const path = this.base(project) + '/proposals/' + encodeURIComponent(proposal);
    return this.unwrap(
      prepare
        ? this.http.post<Envelope<ConfigurationReview>>(path + '/review', {})
        : this.http.get<Envelope<ConfigurationReview>>(path),
    );
  }
  history(project: string): Observable<{
    readonly proposals: readonly ConfigurationProposal[];
    readonly entries: readonly { readonly proposal_id: string; readonly status: string }[];
  }> {
    return this.unwrap(
      this.http.get<
        Envelope<{
          readonly proposals: readonly ConfigurationProposal[];
          readonly entries: readonly { readonly proposal_id: string; readonly status: string }[];
        }>
      >(this.base(project) + '/history'),
    );
  }
  check(
    project: string,
    expected_revision: string,
    request_id: string,
    configuration: LocalConfiguration,
    kind: 'offline' | 'toolchain' | 'provider',
    project_configuration?: ProjectConfiguration,
  ): Observable<ConfigurationCheck> {
    return this.unwrap(
      this.http.post<Envelope<ConfigurationCheck>>(this.base(project) + '/checks', {
        expected_revision,
        request_id,
        configuration,
        kind,
        ...(project_configuration ? { project_configuration } : {}),
      }),
    );
  }
  checkStatus(project: string, operation: string): Observable<ConfigurationCheck> {
    return this.unwrap(
      this.http.get<Envelope<ConfigurationCheck>>(
        this.base(project) + '/checks/' + encodeURIComponent(operation),
      ),
    );
  }
  checkAction(
    project: string,
    operation: string,
    action: 'cancel' | 'recover',
  ): Observable<ConfigurationCheck> {
    return this.unwrap(
      this.http.post<Envelope<ConfigurationCheck>>(
        this.base(project) + '/checks/' + encodeURIComponent(operation) + '/' + action,
        {},
      ),
    );
  }
  setup(project: string, request: SetupRequest): Observable<SetupPlan> {
    return this.unwrap(
      this.http.post<Envelope<SetupPlan>>(this.base(project) + '/setup-plan', request),
    );
  }
  private unwrap<T>(source: Observable<Envelope<T>>): Observable<T> {
    return source.pipe(
      timeout({ first: 15000 }),
      map((response) => {
        if (response.status !== 'ok' || response.data === undefined)
          throw new ApiError('server', 'Configuration service returned an incompatible response.');
        return response.data;
      }),
      catchError((error) => throwError(() => apiError(error))),
    );
  }
}
