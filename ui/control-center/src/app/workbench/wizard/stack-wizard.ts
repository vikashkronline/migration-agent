import type { OnInit } from '@angular/core';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { SessionState } from '../../core/session/session-state';
import { CcIcon } from '../../shared/icon/cc-icon';
import { terminalCommand } from '../../shared/terminal-command';
import { StackWizardApi } from './stack-wizard-api';
import type {
  ArchitecturalDecisionRecord,
  PackageMappingOutcome,
  ProjectStackStatus,
  StackAnalysisResult,
  StackRecommendationDraft,
  StageFoundationResult,
  TargetStackPreset,
  ReplacementStrategy,
} from './stack-wizard.models';

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (
    typeof err === 'object' &&
    err !== null &&
    'message' in err &&
    typeof (err as { message: unknown }).message === 'string'
  ) {
    return (err as { message: string }).message;
  }
  return fallback;
}

export type WizardStepId = 'inventory' | 'preset' | 'matrix' | 'adr' | 'foundation';

export interface WizardStepDef {
  readonly id: WizardStepId;
  readonly number: number;
  readonly title: string;
  readonly subtitle: string;
}

@Component({
  selector: 'cc-stack-wizard',
  standalone: true,
  imports: [RouterLink, CcIcon, FormsModule],
  templateUrl: './stack-wizard.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StackWizardPage implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(StackWizardApi);
  private readonly session = inject(SessionState);
  readonly foundationPlanId = signal('');
  readonly foundationStepId = signal('');
  readonly canWrite = computed(
    () => this.session.session()?.access?.capabilities.includes('knowledge.write') ?? false,
  );
  readonly canAccept = computed(() =>
    ['knowledge.approve', 'access.propose', 'rules.manage'].every(
      (capability) => this.session.session()?.access?.capabilities.includes(capability) === true,
    ),
  );
  readonly canStage = computed(
    () => this.session.session()?.access?.capabilities.includes('changeset.stage') ?? false,
  );

  readonly steps: readonly WizardStepDef[] = [
    { id: 'inventory', number: 1, title: 'Source Inventory', subtitle: 'Inspect legacy packages' },
    { id: 'preset', number: 2, title: 'Target Preset', subtitle: 'Angular 17 baseline' },
    { id: 'matrix', number: 3, title: 'Package Matrix', subtitle: 'Dependency replacements' },
    { id: 'adr', number: 4, title: 'Architecture ADRs', subtitle: 'Formal governance records' },
    { id: 'foundation', number: 5, title: 'Foundation Staging', subtitle: 'Generate target files' },
  ];

  readonly projectId = signal<string>('default');
  readonly activeStep = signal<WizardStepId>('inventory');
  readonly loading = signal<boolean>(false);
  readonly actionPending = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly architectureHandoff = signal<readonly string[]>([]);

  readonly analysis = signal<StackAnalysisResult | null>(null);
  readonly status = signal<ProjectStackStatus | null>(null);
  readonly presets = signal<readonly TargetStackPreset[]>([]);
  readonly selectedPresetId = signal<string>('');
  readonly draft = signal<StackRecommendationDraft | null>(null);
  readonly mappingChoices = signal<Readonly<Record<string, ReplacementStrategy>>>({});
  readonly stageResult = signal<StageFoundationResult | null>(null);
  readonly matrixFilter = signal<'all' | 'replace' | 'native' | 'remove'>('all');

  readonly isArchitectureAccepted = computed<boolean>(() => {
    const s = this.status();
    if (s) return s.architecture_accepted;
    const a = this.analysis();
    return Boolean(a?.readiness_status?.architecture_accepted);
  });

  readonly isFoundationStaged = computed<boolean>(() => {
    const s = this.status();
    if (s) return s.foundation_staged;
    if (this.stageResult() !== null) return true;
    const a = this.analysis();
    return Boolean(a?.readiness_status?.foundation_staged);
  });

  readonly adrList = computed<readonly ArchitecturalDecisionRecord[]>(() => {
    const d = this.draft();
    if (d?.decisions && d.decisions.length > 0) {
      return d.decisions;
    }
    const a = this.analysis();
    if (a?.existing_adrs && a.existing_adrs.length > 0) {
      return a.existing_adrs;
    }
    return [];
  });

  readonly filteredMappings = computed<readonly PackageMappingOutcome[]>(() => {
    const d = this.draft();
    if (!d?.custom_mappings) return [];
    const list = Object.values(d.custom_mappings);
    const filter = this.matrixFilter();
    if (filter === 'all') return list;
    return list.filter((m) => m.strategy === filter);
  });

  chooseFoundation(value: string): void {
    const task = this.status()?.foundation_tasks?.find(
      (item) => `${item.plan_id}/${item.step_id}` === value,
    );
    this.foundationPlanId.set(task?.plan_id ?? '');
    this.foundationStepId.set(task?.step_id ?? '');
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('projectId') ?? 'default';
    this.projectId.set(id);

    const stepParam = this.route.snapshot.queryParamMap.get('step');
    if (stepParam && ['inventory', 'preset', 'matrix', 'adr', 'foundation'].includes(stepParam)) {
      this.activeStep.set(stepParam as WizardStepId);
    }

    this.refreshAll();
  }

  refreshAll(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    const pid = this.projectId();
    this.api.getPresets().subscribe({
      next: (res) => {
        this.presets.set(res.presets);
        if (res.default_preset_id && !this.selectedPresetId()) {
          this.selectedPresetId.set(res.default_preset_id);
        }
      },
      error: (err: unknown) => {
        this.errorMessage.set(extractErrorMessage(err, 'Failed to load presets.'));
      },
    });

    this.api.getAnalysis(pid).subscribe({
      next: (res) => {
        this.analysis.set(res);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.errorMessage.set(extractErrorMessage(err, 'Failed to analyze source stack.'));
      },
    });

    this.api.getStatus(pid).subscribe({
      next: (res) => {
        this.status.set(res);
      },
      error: (err: unknown) => {
        this.status.set(null);
        this.stageResult.set(null);
        this.errorMessage.set(
          extractErrorMessage(err, 'Foundation status unavailable; check governance setup.'),
        );
      },
    });

    this.api.getDraft(pid).subscribe({
      next: (d) => {
        this.draft.set(d);
        if (d.preset_id) {
          this.selectedPresetId.set(d.preset_id);
        }
      },
      error: () => {
        // No draft saved yet; that is expected on first run
      },
    });
  }

  setActiveStep(step: WizardStepId): void {
    this.activeStep.set(step);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { step },
      queryParamsHandling: 'merge',
    });
  }

  isStepComplete(stepId: WizardStepId): boolean {
    switch (stepId) {
      case 'inventory':
        return this.analysis() !== null;
      case 'preset':
        return Boolean(this.selectedPresetId() && this.draft() !== null);
      case 'matrix':
        return Boolean(this.draft()?.custom_mappings);
      case 'adr':
        return this.isArchitectureAccepted();
      case 'foundation':
        return this.isFoundationStaged();
    }
  }

  saveDraftAndContinue(nextStep: WizardStepId): void {
    this.actionPending.set(true);
    this.errorMessage.set(null);

    this.api
      .saveDraft(this.projectId(), {
        preset_id: this.selectedPresetId(),
        custom_mappings: this.mappingChoices(),
      })
      .subscribe({
        next: (savedDraft) => {
          this.draft.set(savedDraft);
          this.actionPending.set(false);
          this.successMessage.set('Working draft saved.');
          this.setActiveStep(nextStep);
        },
        error: (err: unknown) => {
          this.actionPending.set(false);
          this.errorMessage.set(extractErrorMessage(err, 'Failed to save stack draft.'));
        },
      });
  }

  changeMapping(name: string, strategy: ReplacementStrategy): void {
    this.mappingChoices.update((choices) => ({ ...choices, [name]: strategy }));
    this.successMessage.set('Mapping edits require saving a new draft and confirming its ADRs.');
  }

  acceptArchitecture(): void {
    if (!this.canAccept()) return;
    this.actionPending.set(true);
    this.errorMessage.set(null);

    const currentDraft = this.draft();
    this.api.acceptArchitecture(this.projectId(), currentDraft?.content_digest).subscribe({
      next: (result) => {
        this.architectureHandoff.set(result.review_command ?? []);
        this.actionPending.set(false);
        this.successMessage.set(
          result.status === 'approval_required'
            ? 'Architecture proposal prepared. Review and sign in your owner terminal, then refresh.'
            : `Architectural decisions accepted: ${result.accepted_decision_ids.join(', ')}`,
        );
        // Refresh status
        this.api.getStatus(this.projectId()).subscribe({
          next: (s) => this.status.set(s),
        });
        if (result.status === 'accepted') this.setActiveStep('foundation');
      },
      error: (err: unknown) => {
        this.actionPending.set(false);
        this.errorMessage.set(extractErrorMessage(err, 'Failed to accept architecture.'));
      },
    });
  }

  architectureCommand(): string {
    return terminalCommand(this.architectureHandoff());
  }

  async copyArchitectureCommand(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.architectureCommand());
      this.successMessage.set('Command copied. Review it in your trusted owner terminal.');
    } catch {
      this.successMessage.set('Clipboard unavailable. Select and copy the displayed command.');
    }
  }

  stageFoundation(): void {
    if (!this.foundationPlanId() || !this.foundationStepId()) {
      this.errorMessage.set(
        'Select the recorded foundation plan and step IDs. Submit a grounded plan through the agent first.',
      );
      return;
    }
    this.actionPending.set(true);
    this.errorMessage.set(null);

    this.api
      .stageFoundation(this.projectId(), {
        plan_id: this.foundationPlanId(),
        step_id: this.foundationStepId(),
        request_id: crypto.randomUUID(),
      })
      .subscribe({
        next: (result) => {
          this.actionPending.set(false);
          this.stageResult.set(result);
          this.successMessage.set(
            `Foundation workspace successfully staged (${result.file_count} files).`,
          );
          // Refresh status
          this.api.getStatus(this.projectId()).subscribe({
            next: (s) => this.status.set(s),
          });
        },
        error: (err: unknown) => {
          this.actionPending.set(false);
          this.errorMessage.set(extractErrorMessage(err, 'Failed to stage foundation workspace.'));
        },
      });
  }
}
