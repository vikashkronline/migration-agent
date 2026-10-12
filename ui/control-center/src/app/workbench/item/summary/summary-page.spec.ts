import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { WorkbenchStore } from '../../workbench-store';
import { WorkbenchApi } from '../../workbench-api';
import { StackWizardApi } from '../../wizard/stack-wizard-api';
import { detailFixture, projectFixture } from '../../workbench.testing';
import type { WorkNode } from '../../workbench.models';
import { of } from 'rxjs';
import { SummaryPage } from './summary-page';

describe('SummaryPage recommendations', () => {
  function setup(nodes: WorkNode[]) {
    const detailSig = signal(detailFixture(projectFixture));
    const nodesSig = signal<readonly WorkNode[]>(nodes);
    const childrenSig = signal(new Map<string | null, readonly WorkNode[]>());

    TestBed.configureTestingModule({
      imports: [SummaryPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: WorkbenchStore,
          useValue: {
            detail: detailSig,
            nodes: nodesSig,
            children: childrenSig,
            node: (id: string) => nodes.find((n) => n.node_id === id) ?? null,
            label: (id: string) => nodes.find((n) => n.node_id === id)?.label ?? id,
          },
        },
        {
          provide: WorkbenchApi,
          useValue: {
            tree: () =>
              of({
                project_id: 'bound',
                revision: 'r1',
                cursor: 0,
                nodes: [],
                ancestors: [],
                total: 0,
                next_offset: null,
              }),
          },
        },
        {
          provide: StackWizardApi,
          useValue: {
            getStatus: () => of(null),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(SummaryPage);
    return { fixture, component: fixture.componentInstance };
  }

  it('recommends Architecture decisions first when knowledge has no references', async () => {
    const nodes: WorkNode[] = [
      projectFixture,
      {
        ...projectFixture,
        node_id: 'foundation',
        label: '1. Foundation & readiness',
        kind: 'group',
      },
      {
        ...projectFixture,
        node_id: 'work',
        label: '2. Workflows & tasks',
        kind: 'group',
      },
      {
        ...projectFixture,
        node_id: 'knowledge',
        label: '3. Architecture & knowledge',
        kind: 'group',
      },
    ];

    const { fixture } = setup(nodes);
    await fixture.whenStable();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Architecture Decisions Required');
    expect(root.textContent).toContain('3. Architecture & knowledge');
    expect(root.textContent).toContain('Open Architecture & Knowledge');
  });

  it('recommends the unapplied prerequisite when an attention task is blocked', async () => {
    const nodes: WorkNode[] = [
      projectFixture,
      {
        ...projectFixture,
        node_id: 'knowledge',
        label: '3. Architecture & knowledge',
        kind: 'group',
      },
      {
        ...projectFixture,
        node_id: 'ref-1',
        parent_id: 'knowledge',
        label: 'ADR-001: Standalone components',
        kind: 'reference',
      },
      {
        ...projectFixture,
        node_id: 'step-001',
        label: 'Initialize modern package dependencies',
        kind: 'task',
        status: 'STAGE_VERIFIED',
        dependencies: [],
      },
      {
        ...projectFixture,
        node_id: 'step-004',
        label: 'Migrate account-panel',
        kind: 'task',
        status: 'VALIDATION_FAILED',
        needs_attention: true,
        dependencies: ['step-001'],
      },
    ];

    const { fixture } = setup(nodes);
    await fixture.whenStable();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    // Should NOT highlight step-004 directly, but its prerequisite step-001!
    expect(root.textContent).toContain('Prerequisite Required');
    expect(root.textContent).toContain('Initialize modern package dependencies');
    expect(root.textContent).toContain('Go to Initialize modern package dependencies');
    expect(root.textContent).toContain('blocked because prerequisite');
  });

  it('recommends attention task when its prerequisites are already applied', async () => {
    const nodes: WorkNode[] = [
      projectFixture,
      {
        ...projectFixture,
        node_id: 'knowledge',
        label: '3. Architecture & knowledge',
        kind: 'group',
      },
      {
        ...projectFixture,
        node_id: 'ref-1',
        parent_id: 'knowledge',
        label: 'ADR-001: Standalone components',
        kind: 'reference',
      },
      {
        ...projectFixture,
        node_id: 'step-001',
        label: 'Initialize modern package dependencies',
        kind: 'task',
        status: 'APPLY_COMPLETED',
        dependencies: [],
      },
      {
        ...projectFixture,
        node_id: 'step-004',
        label: 'Migrate account-panel',
        kind: 'task',
        status: 'VALIDATION_FAILED',
        needs_attention: true,
        dependencies: ['step-001'],
      },
    ];

    const { fixture } = setup(nodes);
    await fixture.whenStable();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Attention Required');
    expect(root.textContent).toContain('Migrate account-panel');
    expect(root.textContent).toContain('Go to Migrate account-panel');
  });
});
