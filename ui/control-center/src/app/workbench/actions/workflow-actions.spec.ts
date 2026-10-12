import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WorkDetail } from '../workbench.models';
import { detailFixture } from '../workbench.testing';
import { WorkbenchStore } from '../workbench-store';
import { WorkflowActions } from './workflow-actions';

describe('Exact action confirmation', () => {
  const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal');
  const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close');
  beforeEach(() => {
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.open = true;
      },
    });
    Object.defineProperty(HTMLDialogElement.prototype, 'close', {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.open = false;
      },
    });
  });
  afterEach(() => {
    if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal');
    if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close');
    document.body.style.overflow = '';
  });

  it('closes a confirmation when its evidence changes and sends no action', async () => {
    const state = {
      detail: signal<WorkDetail | null>(detailFixture()),
      fresh: signal(true),
      pending: signal(false),
      command: signal(null),
      requestAction: vi.fn(),
    };
    TestBed.configureTestingModule({ providers: [{ provide: WorkbenchStore, useValue: state }] });
    const fixture = TestBed.createComponent(WorkflowActions);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    root.querySelector<HTMLButtonElement>('button.btn-outline-primary')?.click();
    await fixture.whenStable();
    expect(root.querySelector('dialog')?.open).toBe(true);
    state.detail.set({ ...detailFixture(), changeset_digest: 'new-digest' });
    await fixture.whenStable();
    expect(root.querySelector('dialog')?.open).toBe(false);
    expect(state.requestAction).not.toHaveBeenCalled();
  });

  it('keeps unavailable actions disabled even with a current session', async () => {
    const detail = detailFixture();
    const state = {
      detail: signal({
        ...detail,
        actions: detail.actions.map((action) => ({ ...action, available: false })),
      }),
      fresh: signal(true),
      pending: signal(false),
      command: signal(null),
      requestAction: vi.fn(),
    };
    TestBed.configureTestingModule({ providers: [{ provide: WorkbenchStore, useValue: state }] });
    const fixture = TestBed.createComponent(WorkflowActions);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(root.querySelector<HTMLButtonElement>('button.btn-outline-primary')?.disabled).toBe(
      true,
    );
  });
});
