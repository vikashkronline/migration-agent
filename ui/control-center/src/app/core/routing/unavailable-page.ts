import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Feedback } from '../../shared/feedback/feedback';
import { SessionAuth } from '../session/session-auth';
import { SessionState } from '../session/session-state';

const reasons: Readonly<Record<string, string>> = {
  project:
    'Selected project is outside this session. Open the bound project from the trusted launcher.',
  session: 'Your local session is unavailable or expired. Reconnect below or reopen the launcher.',
  forbidden: 'Your session is not permitted to open this project.',
  offline: 'The local service is unavailable. Reconnect or restart the trusted launcher.',
};

@Component({
  selector: 'cc-unavailable-page',
  imports: [Feedback, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main class="container py-5">
      <h1 class="h3">Control Center unavailable</h1>
      <cc-feedback title="Context unavailable" [message]="message()" />

      @if (isSession()) {
        <div class="card p-4 mt-4 mb-3 shadow-sm border-secondary-subtle" style="max-width: 580px;">
          <h2 class="h5 mb-2">Reconnect Local Session</h2>
          <p class="small text-muted mb-3">
            Your browser session token was cleared or not detected. If you launched the Control
            Center with a token, paste it here to reconnect immediately.
          </p>

          @if (connectionError()) {
            <div class="alert alert-danger py-2 px-3 small mb-3">
              {{ connectionError() }}
            </div>
          }

          <div class="mb-3">
            <label for="session-token-input" class="form-label small fw-bold">Session Token</label>
            <div class="input-group">
              <input
                id="session-token-input"
                type="text"
                class="form-control font-monospace form-control-sm"
                placeholder="e.g. session-secret-token-abcdef123456"
                [value]="tokenInput()"
                (input)="onTokenChange($event)"
                (keydown.enter)="connect()"
              />
              <button
                class="btn btn-primary btn-sm px-3"
                type="button"
                [disabled]="!tokenInput().trim() || isConnecting()"
                (click)="connect()"
              >
                @if (isConnecting()) {
                  <span class="spinner-border spinner-border-sm me-1"></span>
                  Connecting...
                } @else {
                  Connect
                }
              </button>
            </div>
          </div>
        </div>
      }

      <div class="mt-3">
        <a class="btn btn-outline-primary" routerLink="/">Open bound project</a>
      </div>
    </main>
  `,
})
export class UnavailablePage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly auth = inject(SessionAuth);
  private readonly sessionState = inject(SessionState);
  private readonly query = toSignal(this.route.queryParamMap, {
    initialValue: this.route.snapshot.queryParamMap,
  });

  protected readonly isSession = computed(() => this.query().get('reason') === 'session');
  protected readonly tokenInput = signal('');
  protected readonly isConnecting = signal(false);
  protected readonly connectionError = signal<string | null>(null);

  protected readonly message = computed(
    () =>
      reasons[this.query().get('reason') ?? ''] ??
      'This destination is missing or unsupported. No replacement context was selected.',
  );

  protected onTokenChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.tokenInput.set(input.value);
  }

  protected connect(): void {
    const token = this.tokenInput().trim();
    if (!token) return;
    this.isConnecting.set(true);
    this.connectionError.set(null);
    this.auth.setToken(token);
    this.sessionState.reset();
    this.sessionState.ensure().subscribe({
      next: (session) => {
        this.isConnecting.set(false);
        void this.router.navigate(['/projects', session.project_id, 'items', 'project']);
      },
      error: () => {
        this.isConnecting.set(false);
        this.connectionError.set(
          'Failed to authenticate: Invalid session token or server not responding. Please check your token.',
        );
      },
    });
  }
}
