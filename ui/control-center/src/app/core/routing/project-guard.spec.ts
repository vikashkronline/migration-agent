import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter, withRouterConfig } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { describe, expect, it, vi } from 'vitest';
import { APP_ROUTES } from '../../app.routes';

describe('Real router project scope', () => {
  it('rejects a foreign project deep link before reading that project', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter(APP_ROUTES, withRouterConfig({ paramsInheritanceStrategy: 'always' })),
      ],
    });
    const http = TestBed.inject(HttpTestingController),
      harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl('/projects/foreign/items/task-a/decision');
    const request = await vi.waitFor(() => http.expectOne('/api/v1/session'));
    request.flush({
      status: 'ok',
      data: { project_id: 'bound', actor: 'operator', assurance: 'MODE_B' },
    });
    await navigation;
    expect(TestBed.inject(Router).url).toContain('/unavailable?reason=project');
    expect(harness.routeNativeElement?.textContent).toContain('Selected project');
    http.verify();
  });
});
