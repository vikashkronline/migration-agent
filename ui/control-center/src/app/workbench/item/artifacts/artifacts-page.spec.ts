import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { detailFixture } from '../../workbench.testing';
import { WorkbenchStore } from '../../workbench-store';
import { ArtifactsPage } from './artifacts-page';

describe('Artifact text rendering', () => {
  it('renders proposed markup as text without executing or creating its elements', async () => {
    const state = { detail: signal(detailFixture()) };
    TestBed.configureTestingModule({
      imports: [ArtifactsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: WorkbenchStore, useValue: state },
      ],
    });
    await TestBed.compileComponents();
    const fixture = TestBed.createComponent(ArtifactsPage);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('pre')?.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(root.querySelector('img')).toBeNull();
  });
});
