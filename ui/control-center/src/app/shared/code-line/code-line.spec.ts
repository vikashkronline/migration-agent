import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { CodeLine } from './code-line';

describe('CodeLine component', () => {
  it('hides standard LF line ending badge by default', async () => {
    const fixture = TestBed.createComponent(CodeLine);
    fixture.componentRef.setInput('text', 'const a = 1;\n');
    fixture.componentRef.setInput('showEnding', false);
    await fixture.whenStable();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('const a = 1;');
    expect(root.textContent).not.toContain('[LF]');
    expect(root.textContent).not.toContain('[CRLF]');
  });

  it('shows [LF] badge when showEnding is toggled on', async () => {
    const fixture = TestBed.createComponent(CodeLine);
    fixture.componentRef.setInput('text', 'const a = 1;\n');
    fixture.componentRef.setInput('showEnding', true);
    await fixture.whenStable();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('[LF]');
  });

  it('always highlights non-standard CRLF line endings even when showEnding is false', async () => {
    const fixture = TestBed.createComponent(CodeLine);
    fixture.componentRef.setInput('text', 'const a = 1;\r\n');
    fixture.componentRef.setInput('showEnding', false);
    await fixture.whenStable();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('[CRLF]');
    const badge = root.querySelector('.badge.text-bg-warning');
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe('[CRLF]');
  });
});
