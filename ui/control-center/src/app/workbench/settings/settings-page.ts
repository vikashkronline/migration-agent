import { JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, exhaustMap, filter, finalize, tap, timer } from 'rxjs';
import { SessionState } from '../../core/session/session-state';
import { apiError } from '../../core/api/api-error';
import { ModalDialog } from '../../shared/modal-dialog/modal-dialog';
import { SettingsApi } from './settings-api';
import { terminalCommand } from '../../shared/terminal-command';
import type {
  ConfigurationCheck,
  ConfigurationDiagnostic,
  ConfigurationProposal,
  ConfigurationReceipt,
  ConfigurationReview,
  ConfigurationView,
  LocalConfiguration,
  ProjectConfiguration,
  RuntimeProfile,
  SetupPlan,
  SetupRequest,
} from './settings.models';

@Component({
  selector: 'cc-settings-page',
  imports: [JsonPipe, FormsModule, RouterLink, ModalDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings-page.html',
})
export class SettingsPage {
  private readonly api = inject(SettingsApi);
  private readonly route = inject(ActivatedRoute);
  private readonly session = inject(SessionState);
  private readonly destroyRef = inject(DestroyRef);
  readonly projectId = this.session.require().project_id;
  readonly section = signal('overview');
  readonly sections = [
    'overview',
    'models',
    'directories',
    'environment',
    'validation',
    'workflow',
    'governance',
    'history',
  ] as const;
  readonly view = signal<ConfigurationView | null>(null);
  readonly projectDraft = signal<ProjectConfiguration | null>(null);
  readonly localDraft = signal<LocalConfiguration | null>(null);
  readonly projectDirty = computed(
    () => JSON.stringify(this.projectDraft()) !== JSON.stringify(this.view()?.project),
  );
  readonly localDirty = computed(
    () => JSON.stringify(this.localDraft()) !== JSON.stringify(this.view()?.local),
  );
  readonly dirty = computed(
    () => Boolean(this.view()) && (this.projectDirty() || this.localDirty()),
  );
  readonly leavePrompt = signal(false);
  private leaveResolve: ((leave: boolean) => void) | null = null;
  readonly stale = signal(false);
  readonly pending = signal(false);
  readonly disconnected = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly outcomeUnknown = signal(false);
  readonly review = signal<ConfigurationReview | null>(null);
  readonly history = signal<readonly ConfigurationProposal[]>([]);
  readonly historyEntries = signal<
    readonly { readonly proposal_id: string; readonly status: string }[]
  >([]);
  readonly check = signal<ConfigurationCheck | null>(null);
  readonly confirmation = signal<'provider' | 'toolchain' | null>(null);
  readonly setupPlan = signal<SetupPlan | null>(null);
  readonly setupDraft = signal<SetupRequest>({
    source_root: '',
    governance_root: '',
    state_dir: '',
    staging_root: '',
    project_name: 'migration-project',
  });
  private baseRevision = '';
  private requestId = '';
  private replay: {
    kind: 'local' | 'project' | 'check';
    revision: string;
    id: string;
    local: LocalConfiguration;
    project: ProjectConfiguration;
    checkKind: 'offline' | 'toolchain' | 'provider';
    includeProject: boolean;
  } | null = null;
  readonly canPropose = computed(() => this.has('configuration.propose'));
  readonly canLocal = computed(() => this.has('configuration.local.write'));
  readonly canModels = computed(() => this.canLocal() && this.has('provider.use'));
  readonly canEnvironment = computed(
    () => this.canLocal() && this.has('execution.consent') && this.has('validation.run'),
  );
  readonly canApprove = computed(() =>
    Boolean(this.view()?.is_owner && this.has('rules.manage') && this.has('access.commit')),
  );
  readonly editable = computed(
    () => !this.pending() && !this.stale() && !this.disconnected() && !this.outcomeUnknown(),
  );
  readonly selectedProfile = computed(() => {
    const local = this.localDraft(),
      project = this.view()?.project;
    return project?.profiles.find(
      (p) => p.profile_id === (local?.profile_id || project.default_profile),
    );
  });
  readonly localFields = computed(
    () =>
      this.view()?.field_descriptors.filter(
        (f) =>
          f.scope === 'local' &&
          (f.section === this.section() ||
            (this.section() === 'validation' && f.name === 'native_browser_path')),
      ) ?? [],
  );
  readonly diagnostics = computed<readonly ConfigurationDiagnostic[]>(
    () => this.check()?.diagnostics ?? this.view()?.effective.diagnostics ?? [],
  );
  readonly projectErrors = computed(() => {
    const draft = this.projectDraft();
    if (!draft) return [];
    const errors: string[] = [];
    if (!Number.isInteger(draft.max_turns) || draft.max_turns < 1 || draft.max_turns > 30)
      errors.push('Shared turn limit must be a whole number from 1 to 30.');
    if (
      !Number.isInteger(draft.max_step_files) ||
      draft.max_step_files < 1 ||
      draft.max_step_files > 100
    )
      errors.push(
        'Shared file limit must be a whole number from 1 to 100 and within signed policy.',
      );
    const ids = draft.profiles.map((profile) => profile.profile_id);
    if (new Set(ids).size !== ids.length || ids.some((id) => !/^[a-z][a-z0-9_-]{0,63}$/.test(id)))
      errors.push('Use unique profile identifiers starting with a lowercase letter.');
    if (draft.default_profile && !ids.includes(draft.default_profile))
      errors.push('Select a default profile included in the approved profiles.');
    if (
      draft.profiles.some(
        (profile) =>
          !profile.models.length ||
          !profile.models.includes(profile.default_model) ||
          !profile.allowed_payloads.length,
      )
    )
      errors.push(
        'Each profile needs allowed models, an included default and explicit data purposes.',
      );
    return errors;
  });
  readonly localErrors = computed(() => {
    const local = this.localDraft();
    const maximum = this.view()?.project.max_turns ?? 1;
    return local?.max_turns !== null &&
      local?.max_turns !== undefined &&
      (!Number.isInteger(local.max_turns) || local.max_turns < 1 || local.max_turns > maximum)
      ? [`My turn limit must be a whole number from 1 to ${maximum}.`]
      : [];
  });

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const section = params.get('section') || 'overview';
      this.section.set(
        this.sections.includes(section as (typeof this.sections)[number]) ? section : 'overview',
      );
      if (section === 'history') this.loadHistory();
    });
    this.refresh(true);
    timer(15000, 15000)
      .pipe(
        filter(() => !this.pending()),
        exhaustMap(() =>
          this.api.view(this.projectId).pipe(
            tap((view) => this.receive(view, false)),
            catchError((error) => {
              this.disconnected.set(true);
              this.error.set(apiError(error).message);
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
    timer(1000, 1000)
      .pipe(
        filter(() =>
          Boolean(
            this.check() &&
              ['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'].includes(this.check()!.status),
          ),
        ),
        exhaustMap(() =>
          this.api.checkStatus(this.projectId, this.check()!.operation_id).pipe(
            tap((check) => this.check.set(check)),
            catchError(() => {
              this.message.set(
                'Check response unavailable. Recover this recorded operation before starting another.',
              );
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  has(capability: string): boolean {
    return this.view()?.capabilities.includes(capability) ?? false;
  }
  effective(name: string): string {
    const field = this.view()?.effective.fields.find((f) => f.name === name);
    return field ? `${field.value ?? 'Not selected'} · ${field.origin}` : 'Not selected';
  }
  localValue(name: string): string | number | null {
    const value: unknown = Object.entries(this.localDraft() ?? {}).find(
      ([key]) => key === name,
    )?.[1];
    return typeof value === 'string' || typeof value === 'number' ? value : null;
  }
  updateLocalField(name: string, value: string | number | null): void {
    if (name in (this.localDraft() ?? {}))
      this.changeLocal(name as keyof LocalConfiguration, value);
  }
  modeIsAllowed(mode: string): boolean {
    return this.projectDraft()?.allowed_validation_modes.some((value) => value === mode) ?? false;
  }
  private receive(view: ConfigurationView, replace: boolean): void {
    const retain = this.dirty() || this.outcomeUnknown();
    this.view.set(view);
    this.disconnected.set(false);
    if ((replace || !retain) && !this.outcomeUnknown()) {
      this.projectDraft.set(view.project);
      this.localDraft.set(view.local);
      this.baseRevision = view.revision;
      this.stale.set(false);
    } else if (view.revision !== this.baseRevision) this.stale.set(true);
  }
  refresh(replace = false): void {
    if (this.dirty() && !replace) {
      this.message.set(
        'Your edits are retained. Use Cancel edits to load the current active values.',
      );
      return;
    }
    this.api
      .view(this.projectId)
      .pipe(
        tap((view) => {
          this.receive(view, true);
          this.error.set('');
        }),
        catchError((error) => {
          this.error.set(apiError(error).message);
          this.disconnected.set(true);
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  cancelEdits(): void {
    if (this.outcomeUnknown() || this.pending()) return;
    this.requestId = '';
    this.refresh(true);
  }
  changeLocal(name: keyof LocalConfiguration, value: string | number | null): void {
    const current = this.localDraft();
    if (!current || name === 'schema_version') return;
    this.localDraft.set({ ...current, [name]: value === '' ? null : value });
    this.edited();
  }
  changeProject(name: keyof ProjectConfiguration, value: string | number | boolean | null): void {
    const current = this.projectDraft();
    if (!current) return;
    this.projectDraft.set({ ...current, [name]: value === '' ? null : value });
    this.edited();
  }
  private edited(): void {
    this.error.set('');
    this.message.set('');
    this.check.set(null);
    this.review.set(null);
    this.requestId = '';
  }
  newProfile(): void {
    const current = this.projectDraft();
    if (!current) return;
    this.projectDraft.set({
      ...current,
      profiles: [
        ...current.profiles,
        {
          profile_id: 'runtime-' + (current.profiles.length + 1),
          provider: 'gemini',
          models: [],
          default_model: '',
          allowed_payloads: ['connectivity'],
        },
      ],
    });
    this.edited();
  }
  changeProfile(index: number, field: keyof RuntimeProfile, value: string): void {
    const current = this.projectDraft();
    if (!current) return;
    const profiles = current.profiles.map((profile, i) =>
      i === index
        ? {
            ...profile,
            [field]:
              field === 'models'
                ? value
                    .split(',')
                    .map((v) => v.trim())
                    .filter(Boolean)
                : value,
          }
        : profile,
    );
    this.projectDraft.set({ ...current, profiles });
    this.edited();
  }
  removeProfile(index: number): void {
    const current = this.projectDraft();
    if (current) {
      this.projectDraft.set({
        ...current,
        profiles: current.profiles.filter((_, i) => index !== i),
      });
      this.edited();
    }
  }
  payloadAllowed(index: number, payload: string, checked: boolean): void {
    const current = this.projectDraft();
    if (!current) return;
    const profiles = current.profiles.map((profile, i) =>
      i === index
        ? {
            ...profile,
            allowed_payloads: (checked
              ? [...profile.allowed_payloads, payload]
              : profile.allowed_payloads.filter(
                  (value) => value !== payload,
                )) as RuntimeProfile['allowed_payloads'],
          }
        : profile,
    );
    this.projectDraft.set({ ...current, profiles });
    this.edited();
  }
  payloadIsAllowed(profile: RuntimeProfile, payload: string): boolean {
    return profile.allowed_payloads.some((value) => value === payload);
  }
  modeAllowed(mode: string, checked: boolean): void {
    const current = this.projectDraft();
    if (!current) return;
    const modes = checked
      ? [...current.allowed_validation_modes, mode]
      : current.allowed_validation_modes.filter((value) => value !== mode);
    this.projectDraft.set({
      ...current,
      allowed_validation_modes: modes as ProjectConfiguration['allowed_validation_modes'],
    });
    this.edited();
  }
  private mutation(kind: 'local' | 'project', retry = false): void {
    if (
      this.pending() ||
      (!retry && !this.editable()) ||
      (kind === 'local' ? !this.canLocal() : !this.canPropose())
    )
      return;
    if (!retry && (kind === 'project' ? this.projectErrors().length : this.localErrors().length))
      return;
    if (!retry) this.capture(kind, 'offline');
    const exact = this.replay;
    if (!exact) return;
    this.pending.set(true);
    const request =
      kind === 'local'
        ? this.api.local(this.projectId, exact.revision, exact.id, exact.local)
        : this.api.propose(this.projectId, exact.revision, exact.id, exact.project);
    request
      .pipe(
        tap((receipt) => this.saved(receipt)),
        catchError((error) => {
          const problem = apiError(error);
          this.error.set(problem.message);
          if (problem.kind === 'stale') this.stale.set(true);
          this.outcomeUnknown.set(problem.kind === 'offline' || problem.kind === 'server');
          if (!this.outcomeUnknown()) this.replay = null;
          return EMPTY;
        }),
        finalize(() => this.pending.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  saveLocal(): void {
    this.mutation('local');
  }
  propose(): void {
    this.mutation('project');
  }
  private saved(receipt: ConfigurationReceipt): void {
    const savedKind = this.replay?.kind;
    this.replay = null;
    this.outcomeUnknown.set(false);
    this.message.set(receipt.message);
    this.requestId = '';
    if (receipt.proposal_id) {
      this.projectDraft.set(this.view()!.project);
      this.openReview(receipt.proposal_id, false);
    } else {
      const shared = this.projectDraft();
      const retainShared = savedKind === 'local' && this.projectDirty();
      this.api
        .view(this.projectId)
        .pipe(
          tap((view) => {
            this.receive(view, true);
            if (retainShared) this.projectDraft.set(shared);
          }),
          catchError((error) => {
            this.error.set(apiError(error).message);
            return EMPTY;
          }),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe();
    }
  }
  retryUnknown(): void {
    if (!this.outcomeUnknown() || !this.replay || this.pending()) return;
    const kind = this.replay.kind;
    if (kind === 'check') this.startCheck(this.replay.checkKind, true);
    else this.mutation(kind, true);
  }
  openReview(proposal: string, prepare: boolean): void {
    if (prepare && (!this.canApprove() || this.disconnected() || this.pending())) return;
    this.api
      .review(this.projectId, proposal, prepare)
      .pipe(
        tap((review) => this.review.set(review)),
        catchError((error) => {
          this.error.set(apiError(error).message);
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  loadHistory(): void {
    this.api
      .history(this.projectId)
      .pipe(
        tap((result) => {
          this.history.set(result.proposals);
          this.historyEntries.set(result.entries);
        }),
        catchError((error) => {
          this.error.set(apiError(error).message);
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  historyStatus(proposal: string): string {
    return this.historyEntries().find((entry) => entry.proposal_id === proposal)?.status ?? 'DRAFT';
  }
  restoreDraft(proposal: ConfigurationProposal): void {
    if (!this.canPropose()) return;
    this.projectDraft.set(proposal.configuration);
    this.edited();
    this.message.set(
      'Historical settings copied into a new draft. Validate and obtain a new owner signature; the active pointer is unchanged.',
    );
  }
  runCheck(kind: 'offline' | 'toolchain' | 'provider'): void {
    if (!this.localDraft() || this.pending() || this.stale() || this.disconnected()) return;
    if (kind !== 'offline') {
      this.confirmation.set(kind);
      return;
    }
    this.startCheck(kind);
  }
  confirmProbe(): void {
    const kind = this.confirmation();
    this.confirmation.set(null);
    if (kind) this.startCheck(kind);
  }
  private startCheck(kind: 'offline' | 'toolchain' | 'provider', retry = false): void {
    if (this.pending()) return;
    if (!retry) this.capture('check', kind);
    const exact = this.replay;
    if (!exact) return;
    this.pending.set(true);
    this.api
      .check(
        this.projectId,
        exact.revision,
        exact.id,
        exact.local,
        kind,
        exact.includeProject ? exact.project : undefined,
      )
      .pipe(
        tap((check) => {
          this.check.set(check);
          this.requestId = '';
          this.outcomeUnknown.set(false);
          this.replay = null;
        }),
        catchError((error) => {
          const problem = apiError(error);
          this.error.set(problem.message);
          if (problem.kind === 'stale') this.stale.set(true);
          this.outcomeUnknown.set(problem.kind === 'offline' || problem.kind === 'server');
          if (!this.outcomeUnknown()) this.replay = null;
          return EMPTY;
        }),
        finalize(() => this.pending.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  checkAction(action: 'cancel' | 'recover'): void {
    const check = this.check();
    if (check)
      this.api
        .checkAction(this.projectId, check.operation_id, action)
        .pipe(
          tap((result) => this.check.set(result)),
          catchError((error) => {
            this.error.set(apiError(error).message);
            return EMPTY;
          }),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe();
  }
  changeSetup(name: keyof SetupRequest, value: string): void {
    this.setupDraft.update((draft) => ({ ...draft, [name]: value }));
    this.setupPlan.set(null);
  }
  prepareSetup(): void {
    if (!this.canApprove()) return;
    this.api
      .setup(this.projectId, this.setupDraft())
      .pipe(
        tap((plan) => this.setupPlan.set(plan)),
        catchError((error) => {
          this.error.set(apiError(error).message);
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  command(arguments_: readonly string[]): string {
    const windows = this.view()?.bindings['source_root']?.includes('\\');
    return terminalCommand(arguments_, windows);
  }
  async copy(arguments_: readonly string[]): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.command(arguments_));
      this.message.set('Command copied. Review the exact arguments in your trusted terminal.');
    } catch {
      this.message.set('Clipboard unavailable. Select and copy the displayed argument list.');
    }
  }
  private capture(
    kind: 'local' | 'project' | 'check',
    checkKind: 'offline' | 'toolchain' | 'provider',
  ): void {
    this.requestId = crypto.randomUUID();
    this.replay = {
      kind,
      checkKind,
      includeProject:
        kind === 'check' && checkKind === 'offline' && this.projectDirty() && this.canPropose(),
      id: this.requestId,
      revision: this.baseRevision,
      local: structuredClone(this.localDraft()!),
      project: structuredClone(this.projectDraft()!),
    };
  }
  canLeave(): boolean | Promise<boolean> {
    if (!this.dirty() && !this.pending() && !this.outcomeUnknown()) return true;
    this.leavePrompt.set(true);
    return new Promise<boolean>((resolve) => {
      this.leaveResolve = resolve;
    });
  }
  finishLeave(leave: boolean): void {
    this.leavePrompt.set(false);
    this.leaveResolve?.(leave);
    this.leaveResolve = null;
  }
}
