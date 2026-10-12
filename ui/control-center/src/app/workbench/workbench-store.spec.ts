import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { SessionState } from '../core/session/session-state';
import { detailFixture, pageFixture, projectFixture, taskFixture } from './workbench.testing';
import { WorkbenchStore } from './workbench-store';

describe('Workbench scoped state', () => {
  let store: WorkbenchStore, http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), WorkbenchStore],
    });
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(SessionState).ensure().subscribe();
    http.expectOne('/api/v1/session').flush({
      status: 'ok',
      data: { project_id: 'bound', actor: 'operator', assurance: 'MODE_B' },
    });
    store = TestBed.inject(WorkbenchStore);
    store.start();
    http
      .expectOne((request) => request.url.endsWith('/tree'))
      .flush({ status: 'ok', data: pageFixture });
    http
      .expectOne((request) => request.url.endsWith('/detail'))
      .flush({ status: 'ok', data: detailFixture(projectFixture) });
  });

  it('cancels a superseded selection so its evidence cannot replace the new item', () => {
    store.select({ nodeId: 'task-a', artifact: null, run: null });
    const previous = http.expectOne((request) => request.url.endsWith('/detail'));
    store.select({ nodeId: 'task-b', artifact: null, run: null });
    expect(previous.cancelled).toBe(true);
    const node = { ...taskFixture, node_id: 'task-b', label: 'New selection' };
    http
      .expectOne((request) => request.url.endsWith('/detail'))
      .flush({ status: 'ok', data: detailFixture(node) });
    expect(store.detail()?.node.node_id).toBe('task-b');
    http.verify({ ignoreCancelled: true });
  });

  it('invalidates a pinned artifact instead of replacing it with a newer digest', () => {
    store.select({ nodeId: 'task-a', artifact: 'old-digest', run: 'run-1' });
    http
      .expectOne((request) => request.url.endsWith('/detail'))
      .flush({ status: 'ok', data: detailFixture() });
    expect(store.detail()).toBeNull();
    expect(store.detailError()?.kind).toBe('stale');
    http.verify();
  });

  it('recovers an uncertain command using exactly the same request identity', () => {
    store.select({ nodeId: 'task-a', artifact: null, run: null });
    const detail = detailFixture();
    http
      .expectOne((request) => request.url.endsWith('/detail'))
      .flush({ status: 'ok', data: detail });
    store.requestAction(detail, 'apply');
    const first = http.expectOne('/api/v1/workbench/command');
    const original: unknown = first.request.body;
    first.error(new ProgressEvent('error'));
    expect(store.command()?.outcome).toBe('unknown');
    store.retryCommand();
    const second = http.expectOne('/api/v1/workbench/command');
    expect(second.request.body).toEqual(original);
    second.flush({
      status: 'ok',
      data: { operation_id: 'op', status: 'SUCCEEDED', message: 'Durable result' },
    });
    http
      .expectOne((request) => request.url.endsWith('/tree'))
      .flush({ status: 'ok', data: pageFixture });
    http
      .expectOne((request) => request.url.endsWith('/detail'))
      .flush({ status: 'ok', data: detail });
    expect(store.command()?.receipt?.operation_id).toBe('op');
    http.verify();
  });

  it('keeps unloaded totals truthful while paging children', () => {
    const parent = {
      ...projectFixture,
      node_id: 'large',
      label: 'Large group',
      kind: 'group' as const,
      child_count: 1000,
      task_count: 1000,
    };
    store.toggle(parent);
    http
      .expectOne((request) => request.url.endsWith('/tree'))
      .flush({
        status: 'ok',
        data: { ...pageFixture, nodes: [taskFixture], total: 1000, next_offset: 100 },
      });
    expect(store.branchPages().get('large')?.next).toBe(100);
    store.loadBranch('large', true);
    const next = http.expectOne((request) => request.url.endsWith('/tree'));
    expect(next.request.params.get('offset')).toBe('100');
    next.flush({
      status: 'ok',
      data: { ...pageFixture, nodes: [], total: 1000, next_offset: null },
    });
    expect(store.branchPages().get('large')?.next).toBeNull();
    http.verify();
  });
});
