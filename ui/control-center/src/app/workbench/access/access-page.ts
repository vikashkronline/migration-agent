import { DatePipe, JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import type { OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin, switchMap, timer, of, EMPTY, catchError } from 'rxjs';
import type { Observable } from 'rxjs';
import { apiError } from '../../core/api/api-error';
import { AccessApi } from './access-api';
import { terminalCommand } from '../../shared/terminal-command';
import type {
  AccessDecision,
  AccessMember,
  AccessMutation,
  AccessPolicy,
  AccessReview,
  AccessRole,
  DirectoryRequest,
  DirectoryResult,
  OnboardingPacket,
} from './access.models';

@Component({
  selector: 'cc-access-page',
  imports: [JsonPipe, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './access-page.html',
})
export class AccessPage implements OnInit {
  private readonly api = inject(AccessApi);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly policy = signal<AccessPolicy | null>(null);
  protected readonly session = signal<AccessDecision | null>(null);
  protected readonly catalog = signal<readonly string[]>([]);
  protected readonly review = signal<AccessReview | null>(null);
  protected readonly directory = signal<DirectoryResult | null>(null);
  protected readonly repositoryPreview = signal<DirectoryResult | null>(null);
  protected readonly error = signal('');
  protected readonly busy = signal(false);
  protected readonly editingMember = signal<AccessMember | null>(null);
  protected readonly editingRole = signal<AccessRole | null>(null);
  protected readonly onboarding = signal<OnboardingPacket | null>(null);

  protected prepareOnboarding(principal: string): void {
    this.onboarding.set(null);
    this.busy.set(true);
    this.api.onboarding(principal).subscribe({
      next: (packet) => {
        this.onboarding.set(packet);
        this.busy.set(false);
      },
      error: (error: unknown) => {
        this.error.set(apiError(error).message);
        this.busy.set(false);
      },
    });
  }
  protected readonly selected = signal<ReadonlySet<string>>(new Set());
  protected readonly canManage = computed(
    () => this.session()?.capabilities.includes('access.propose') === true,
  );
  protected readonly canDirectory = computed(
    () => this.session()?.capabilities.includes('directory.read') === true,
  );
  protected readonly command = computed(() => {
    const review = this.review();
    if (!review) return '';
    return terminalCommand(review.review_command);
  });

  ngOnInit(): void {
    this.refresh();
    timer(15000, 15000)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        switchMap(() =>
          this.api.session().pipe(
            catchError((error: unknown) => {
              this.session.set(null);
              this.policy.set(null);
              this.review.set(null);
              this.error.set(apiError(error).message);
              return EMPTY;
            }),
          ),
        ),
      )
      .subscribe({
        next: (session) => {
          if (session.access_digest !== this.session()?.access_digest) {
            this.review.set(null);
            this.editingMember.set(null);
            this.editingRole.set(null);
            this.directory.set(null);
            this.selected.set(new Set());
            this.refresh();
          }
          this.session.set(session);
        },
        error: (error: unknown) => {
          this.session.set(null);
          this.policy.set(null);
          this.error.set(apiError(error).message);
        },
      });
  }
  protected refresh(): void {
    this.busy.set(true);
    this.error.set('');
    this.api
      .session()
      .pipe(
        switchMap((session) => {
          if (this.session()?.access_digest !== session.access_digest) {
            this.review.set(null);
            this.editingMember.set(null);
            this.editingRole.set(null);
            this.directory.set(null);
            this.selected.set(new Set());
          }
          this.session.set(session);
          if (!session.capabilities.includes('access.read')) return of(null);
          return forkJoin({ policy: this.api.policy(), catalog: this.api.catalog() });
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (data) => {
          this.policy.set(data?.policy ?? null);
          this.catalog.set(data?.catalog ?? []);
          this.busy.set(false);
        },
        error: (error: unknown) => {
          this.policy.set(null);
          this.session.set(null);
          this.error.set(apiError(error).message);
          this.busy.set(false);
        },
      });
  }
  private submit(request: Observable<AccessReview>): void {
    if (this.busy() || !this.canManage()) return;
    this.busy.set(true);
    this.error.set('');
    request.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (review) => {
        this.review.set(review);
        this.busy.set(false);
      },
      error: (error: unknown) => {
        this.review.set(null);
        this.error.set(apiError(error).message);
        this.busy.set(false);
      },
    });
  }
  private mutate(mutations: readonly AccessMutation[]): void {
    const digest = this.session()?.access_digest;
    if (digest) this.submit(this.api.propose(digest, mutations));
  }
  protected editMember(member: AccessMember): void {
    this.editingMember.set(member);
  }
  protected editRole(role: AccessRole): void {
    this.editingRole.set(role);
  }
  protected removeMember(member: AccessMember): void {
    this.mutate([{ kind: 'member.remove', entity_id: member.principal_id }]);
  }
  protected removeRole(role: AccessRole): void {
    this.mutate([{ kind: 'role.remove', entity_id: role.role_id }]);
  }
  private form(event: Event): FormData {
    event.preventDefault();
    return new FormData(event.target as HTMLFormElement);
  }
  private text(form: FormData, key: string): string {
    const value = form.get(key);
    return typeof value === 'string' ? value.trim() : '';
  }
  protected saveMember(event: Event): void {
    const data = this.form(event),
      existing = this.editingMember();
    const status = this.text(data, 'status');
    if (!['pending', 'active', 'suspended'].includes(status)) return;
    const expires = this.text(data, 'expires_at');
    const member: AccessMember = {
      principal_id: existing?.principal_id ?? this.text(data, 'principal_id'),
      label: this.text(data, 'label'),
      roles: data.getAll('role').map(String).sort(),
      status: status as AccessMember['status'],
      os_identity: this.text(data, 'os_identity') || null,
      public_key: existing?.public_key ?? null,
      key_fingerprint: existing?.key_fingerprint ?? null,
      git_account: existing?.git_account ?? null,
      expires_at: expires ? Math.floor(new Date(expires).getTime() / 1000) : null,
    };
    this.mutate([{ kind: 'member.set', member }]);
  }
  protected saveRole(event: Event): void {
    const data = this.form(event);
    this.mutate([
      {
        kind: 'role.set',
        role: {
          role_id: this.editingRole()?.role_id ?? this.text(data, 'role_id'),
          label: this.text(data, 'label'),
          capabilities: data.getAll('capability').map(String).sort(),
        },
      },
    ]);
  }
  protected owners(event: Event): void {
    this.mutate([
      { kind: 'owners.set', owners: this.form(event).getAll('owner').map(String).sort() },
    ]);
  }
  protected repository(): void {
    const preview = this.repositoryPreview();
    if (!preview) return;
    this.mutate([
      {
        kind: 'repository.set',
        repository: {
          ...preview.request,
          repository_id: preview.repository_id,
        },
      },
    ]);
  }
  protected previewRepository(event: Event): void {
    const data = this.form(event),
      provider = this.text(data, 'provider');
    if (this.busy() || !this.canManage() || (provider !== 'github' && provider !== 'gitlab'))
      return;
    this.busy.set(true);
    this.error.set('');
    this.repositoryPreview.set(null);
    this.api
      .repositoryPreview({
        provider,
        host: this.text(data, 'host'),
        repository: this.text(data, 'repository'),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.repositoryPreview.set(result);
          this.busy.set(false);
        },
        error: (error: unknown) => {
          this.error.set(apiError(error).message);
          this.busy.set(false);
        },
      });
  }
  protected loadDirectory(event: Event): void {
    const data = this.form(event),
      provider = this.text(data, 'provider');
    if (this.busy() || !this.canDirectory() || (provider !== 'github' && provider !== 'gitlab'))
      return;
    const request: DirectoryRequest = {
      provider,
      host: this.text(data, 'host'),
      repository: this.text(data, 'repository'),
    };
    this.busy.set(true);
    this.error.set('');
    this.directory.set(null);
    this.selected.set(new Set());
    this.api
      .directory(request)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.directory.set(result);
          this.busy.set(false);
        },
        error: (error: unknown) => {
          this.error.set(apiError(error).message);
          this.busy.set(false);
        },
      });
  }
  protected select(accountId: string, event: Event): void {
    const values = new Set(this.selected());
    if ((event.target as HTMLInputElement).checked) values.add(accountId);
    else values.delete(accountId);
    this.selected.set(values);
  }
  protected importMembers(event: Event): void {
    const roles = this.form(event).getAll('role').map(String).sort();
    const directory = this.directory(),
      digest = this.session()?.access_digest;
    if (directory && digest && roles.length && this.selected().size)
      this.submit(
        this.api.importMembers(digest, directory.request, [...this.selected()].sort(), roles),
      );
  }
}
