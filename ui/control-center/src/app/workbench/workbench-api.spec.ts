import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { SessionAuth, sessionInterceptor } from '../core/session/session-auth';
import { WorkbenchApi } from './workbench-api';

describe('Workbench HTTP boundary', () => {
  let api: WorkbenchApi, http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([sessionInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    api = TestBed.inject(WorkbenchApi);
    http = TestBed.inject(HttpTestingController);
  });

  it('removes bootstrap credentials from history and sends them only to the local API', () => {
    history.replaceState(null, '', '/#token=offline-test-fixture');
    document.cookie = 'csrf_token=independent-fixture; Path=/';
    TestBed.inject(SessionAuth).initialize();
    expect(location.href).not.toContain('offline-test-fixture');
    api
      .command({
        project_id: 'bound',
        node_id: 'task-a',
        expected_revision: 'r1',
        request_id: 'request-a',
        kind: 'apply',
        changeset_id: 'cs-1',
      })
      .subscribe();
    const request = http.expectOne('/api/v1/workbench/command');
    expect(request.request.headers.get('X-Session-Token')).toBe('offline-test-fixture');
    expect(request.request.headers.get('X-CSRF-Token')).toBe('independent-fixture');
    request.flush({
      status: 'ok',
      data: { operation_id: 'op', status: 'QUEUED', message: 'Accepted' },
    });
    http.verify();
  });

  it('distinguishes an expired session without exposing arbitrary server messages', () => {
    let message = '';
    api.session().subscribe({
      error: (error: unknown) => {
        message = error instanceof Error ? error.message : '';
      },
    });
    http
      .expectOne('/api/v1/session')
      .flush(
        { error: { message: 'untrusted server text' } },
        { status: 401, statusText: 'Unauthorized' },
      );
    expect(message).toContain('session');
    expect(message).not.toContain('untrusted');
    http.verify();
  });

  it('rejects a malformed response instead of showing fabricated success', () => {
    let failed = false;
    api.session().subscribe({
      error: () => {
        failed = true;
      },
    });
    http.expectOne('/api/v1/session').flush({ status: 'ok' });
    expect(failed).toBe(true);
    http.verify();
  });
});
