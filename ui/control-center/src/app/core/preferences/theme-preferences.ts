import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ThemePreferences {
  private readonly document = inject(DOCUMENT);
  private readonly value = signal<'light' | 'dark'>('light');
  readonly theme = this.value.asReadonly();

  initialize(): void {
    let theme: 'light' | 'dark' = this.document.defaultView?.matchMedia(
      '(prefers-color-scheme: dark)',
    ).matches
      ? 'dark'
      : 'light';
    try {
      const saved = this.document.defaultView?.localStorage.getItem('control-center-theme');
      if (saved === 'light' || saved === 'dark') theme = saved;
    } catch {
      /* Preference storage may be disabled by the browser. */
    }
    this.apply(theme);
  }
  toggle(): void {
    const next = this.value() === 'dark' ? 'light' : 'dark';
    this.apply(next);
    try {
      this.document.defaultView?.localStorage.setItem('control-center-theme', next);
    } catch {
      /* Rendering remains available without storage. */
    }
  }
  private apply(theme: 'light' | 'dark'): void {
    this.value.set(theme);
    this.document.documentElement.dataset['bsTheme'] = theme;
  }
}
