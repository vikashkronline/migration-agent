import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { detailFixture } from '../../workbench.testing';
import { WorkbenchStore } from '../../workbench-store';
import { AskPage } from './ask-page';

describe('Scoped question draft', () => {
  it('preserves a draft across refresh of the same selected item', async () => {
    const state = {
      detail: signal(detailFixture()),
      selection: signal({ nodeId: 'task-a', artifact: 'digest-1', run: 'run-1' }),
      fresh: signal(true),
    };
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: WorkbenchStore, useValue: state },
      ],
    });
    const fixture = TestBed.createComponent(AskPage);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    const input = root.querySelector('textarea');
    if (!input) throw new Error('Question input missing');
    input.value = 'What is the validation evidence?';
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    state.detail.set({ ...detailFixture(), revision: 'r2' });
    await fixture.whenStable();
    expect(input.value).toBe('What is the validation evidence?');
    state.fresh.set(false);
    await fixture.whenStable();
    expect(root.querySelector<HTMLButtonElement>('button[type=submit]')?.disabled).toBe(true);
    TestBed.inject(HttpTestingController).verify();
  });
});
