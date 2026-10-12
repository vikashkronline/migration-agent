import { DOCUMENT } from '@angular/common';
import type { HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

const STORAGE_KEY = 'migration_agent_session_token';

@Injectable({ providedIn: 'root' })
export class SessionAuth {
  private readonly document = inject(DOCUMENT);
  private token = '';

  initialize(): void {
    const window = this.document.defaultView;
    if (!window) return;
    const url = new URL(window.location.href);
    const urlToken =
      new URLSearchParams(url.hash.slice(1)).get('token') ?? url.searchParams.get('token') ?? '';
    if (urlToken) {
      this.token = urlToken;
      try {
        window.sessionStorage.setItem(STORAGE_KEY, urlToken);
      } catch {
        // Storage access may be restricted
      }
      url.hash = '';
      url.searchParams.delete('token');
      window.history.replaceState(null, '', url);
    } else {
      try {
        this.token = window.sessionStorage.getItem(STORAGE_KEY) ?? '';
      } catch {
        this.token = '';
      }
    }
  }

  setToken(token: string): void {
    this.token = token.trim();
    const window = this.document.defaultView;
    if (window && this.token) {
      try {
        window.sessionStorage.setItem(STORAGE_KEY, this.token);
      } catch {
        // Storage access may be restricted
      }
    }
  }

  clearToken(): void {
    this.token = '';
    const window = this.document.defaultView;
    if (window) {
      try {
        window.sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        // Storage access may be restricted
      }
    }
  }

  sessionHeader(): string {
    return this.token;
  }
  csrfHeader(): string {
    return (
      this.document.cookie
        .split('; ')
        .find((value) => value.startsWith('csrf_token='))
        ?.slice(11) ?? ''
    );
  }
}

export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith('/api/v1/')) return next(request);
  const auth = inject(SessionAuth);
  let headers = request.headers;
  if (auth.sessionHeader()) headers = headers.set('X-Session-Token', auth.sessionHeader());
  if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method))
    headers = headers.set('X-CSRF-Token', auth.csrfHeader());
  return next(request.clone({ headers }));
};
