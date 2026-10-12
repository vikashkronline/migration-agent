import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { detailFixture } from '../../workbench.testing';
import { DiffViewer, splitLines } from './diff-viewer';

describe('Read-only exact artifact diff', () => {
  it('pairs changed lines without duplicating context', () => {
    const rows = splitLines([
      { kind: 'context', old_line: 1, new_line: 1, text: 'context\n' },
      { kind: 'remove', old_line: 2, new_line: null, text: 'old\n' },
      { kind: 'add', old_line: null, new_line: 2, text: 'new\n' },
      { kind: 'add', old_line: null, new_line: 3, text: 'extra\n' },
    ]);
    expect(rows).toHaveLength(3);
    expect(rows[1]?.old?.text).toBe('old\n');
    expect(rows[1]?.next?.text).toBe('new\n');
    expect(rows[2]?.old).toBeNull();
  });
  it('cancels superseded file reads and safely renders code with line numbers', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(DiffViewer);
    const detail = { ...detailFixture(), files: ['first.ts', 'next.ts'] };
    fixture.componentRef.setInput('detail', detail);
    await fixture.whenStable();
    const http = TestBed.inject(HttpTestingController);
    const first = http.expectOne(
      (request) => request.url.endsWith('/diff') && request.params.get('index') === '0',
    );
    const root = fixture.nativeElement as HTMLElement;
    const file = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === 'next.ts',
    );
    file?.click();
    await fixture.whenStable();
    expect(first.cancelled).toBe(true);
    const next = http.expectOne((request) => request.params.get('index') === '1');
    expect(next.request.params.get('artifact')).toBe(detail.changeset_digest);
    next.flush({
      status: 'ok',
      data: {
        project_id: detail.project_id,
        node_id: detail.node.node_id,
        revision: detail.revision,
        changeset_digest: detail.changeset_digest,
        base_revision: detail.base_revision,
        path: 'next.ts',
        operation: 'CREATE',
        file_mode: '0644',
        available: true,
        reason: '',
        hunks: [
          {
            old_start: 0,
            old_count: 0,
            new_start: 1,
            new_count: 1,
            lines: [
              { kind: 'add', old_line: null, new_line: 1, text: '<img src=x onerror=alert(1)>' },
            ],
          },
        ],
      },
    });
    await fixture.whenStable();
    expect(root.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(root.textContent).toContain('No final newline');
    expect(root.querySelector('img')).toBeNull();
    file?.click();
    const firstFile = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === 'first.ts',
    );
    firstFile?.click();
    await fixture.whenStable();
    http
      .expectOne((request) => request.params.get('index') === '0')
      .flush({}, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();
    const retry = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === 'Retry diff',
    );
    expect(retry).toBeDefined();
    retry?.click();
    await fixture.whenStable();
    const recovery = http.expectOne((request) => request.params.get('index') === '0');
    expect(recovery.request.params.get('artifact')).toBe(detail.changeset_digest);
    recovery.flush({}, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();
    http.verify();
  });

  it('toggles line endings visibility on demand', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(DiffViewer);
    const detail = { ...detailFixture(), files: ['first.ts'] };
    fixture.componentRef.setInput('detail', detail);
    await fixture.whenStable();
    const http = TestBed.inject(HttpTestingController);
    http
      .expectOne((r) => r.params.get('index') === '0')
      .flush({
        status: 'ok',
        data: {
          project_id: detail.project_id,
          node_id: detail.node.node_id,
          revision: detail.revision,
          changeset_digest: detail.changeset_digest,
          base_revision: detail.base_revision,
          path: 'first.ts',
          operation: 'CREATE',
          file_mode: '0644',
          available: true,
          reason: '',
          hunks: [
            {
              old_start: 0,
              old_count: 0,
              new_start: 1,
              new_count: 1,
              lines: [{ kind: 'add', old_line: null, new_line: 1, text: 'export const x = 42;\n' }],
            },
          ],
        },
      });
    await fixture.whenStable();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).not.toContain('[LF]');

    const toggleBtn = Array.from(root.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Show line endings'),
    );
    expect(toggleBtn).toBeDefined();
    toggleBtn?.click();
    await fixture.whenStable();
    expect(root.textContent).toContain('[LF]');
    expect(toggleBtn?.textContent).toContain('Hide line endings');

    toggleBtn?.click();
    await fixture.whenStable();
    expect(root.textContent).not.toContain('[LF]');
    expect(toggleBtn?.textContent).toContain('Show line endings');
  });
});
