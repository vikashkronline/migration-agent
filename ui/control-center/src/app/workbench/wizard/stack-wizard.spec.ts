import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { describe, expect, it } from 'vitest';
import { SessionState } from '../../core/session/session-state';
import { StackWizardPage } from './stack-wizard';
import { StackWizardApi } from './stack-wizard-api';
import type {
  AcceptArchitectureResult,
  PresetsResult,
  ProjectStackStatus,
  StackAnalysisResult,
  StackRecommendationDraft,
  StageFoundationResult,
} from './stack-wizard.models';

const mockPresets: PresetsResult = {
  presets: [
    {
      preset_id: 'angular-17-lts-bootstrap5',
      display_name: 'Angular 17 LTS (Standalone & Signals)',
      description: 'Production target',
      framework: 'angular',
      framework_version: '17.3.12',
      ui_library: 'bootstrap-5.3',
      state_management: 'signals',
      build_tool: 'angular-build',
      test_runner: 'vitest',
      compatibility_level: 'high',
    },
  ],
  default_preset_id: 'angular-17-lts-bootstrap5',
};

const mockAnalysis: StackAnalysisResult = {
  project_id: 'test-project',
  source_framework: 'ember-classic',
  dependencies: [
    {
      name: 'ember-source',
      version_spec: '~3.28.0',
      category: 'framework',
      is_dev: false,
      detected_in: 'package.json',
      evidence_locations: ['package.json'],
    },
    {
      name: 'bootstrap',
      version_spec: '^4.5.0',
      category: 'ui_styling',
      is_dev: false,
      detected_in: 'package.json',
      evidence_locations: ['package.json'],
    },
  ],
  existing_adrs: [],
  detected_presets: mockPresets.presets,
  unmapped_dependencies: [],
  readiness_status: {
    ready: false,
    architecture_accepted: false,
    foundation_staged: false,
    accepted_decision_ids: [],
  },
};

const mockDraft: StackRecommendationDraft = {
  draft_id: 'draft-abc',
  project_id: 'test-project',
  preset_id: 'angular-17-lts-bootstrap5',
  custom_mappings: {
    bootstrap: {
      legacy_package: 'bootstrap',
      target_packages: [
        {
          package_name: 'bootstrap',
          version_range: '^5.3.3',
        },
      ],
      strategy: 'replace',
      description: 'Modern Bootstrap 5.3',
      suggested_alternatives: [],
      confidence: 0.95,
    },
  },
  decisions: [
    {
      decision_id: 'ADR-001',
      title: 'Target Framework Architecture',
      status: 'PROPOSED',
      context: 'Migrating legacy Ember app',
      decision: 'Adopt Angular 17.3 LTS with Standalone components and Signals',
      consequences: 'Requires Node 20+, clean component boundaries',
    },
    {
      decision_id: 'ADR-002',
      title: 'UI Styling System',
      status: 'PROPOSED',
      context: 'Migrating CSS framework',
      decision: 'Adopt Bootstrap 5.3 with utility classes and component-scoped SCSS',
      consequences: 'Eliminates jQuery dependency',
    },
    {
      decision_id: 'ADR-003',
      title: 'State Management and Reactivity',
      status: 'PROPOSED',
      context: 'Reactivity model',
      decision: 'Use Angular Signals and RxJS interoperability',
      consequences: 'Enables fine-grained OnPush change detection',
    },
  ],
  content_digest: 'digest-draft-12345',
  status: 'draft',
};

const mockStatus: ProjectStackStatus = {
  project_id: 'test-project',
  architecture_accepted: false,
  foundation_staged: false,
  accepted_decision_ids: [],
  ready_for_migration: false,
};

const mockAcceptResult: AcceptArchitectureResult = {
  status: 'accepted',
  accepted_adrs: mockDraft.decisions.map((d) => ({ ...d, status: 'ACCEPTED' })),
  accepted_decision_ids: ['ADR-001', 'ADR-002', 'ADR-003'],
};

const mockStageResult: StageFoundationResult = {
  status: 'staged',
  run_id: 'run-foundation-001',
  staged_directory: '/staging/test-project/run-foundation-001',
  file_count: 5,
  files: ['package.json', 'tsconfig.json', 'angular.json', 'src/main.ts', 'src/index.html'],
  changeset_digest: 'changeset-digest-xyz',
};

describe('StackWizardPage component', () => {
  function setup() {
    let staged = false;
    const mockApi = {
      getPresets: () => of(mockPresets),
      getAnalysis: () => of(mockAnalysis),
      getStatus: () =>
        of({
          ...mockStatus,
          foundation_staged: staged,
          target_root: 'C:/fixture-target',
          foundation_tasks: [
            {
              plan_id: 'plan-1',
              step_id: 'foundation-1',
              title: 'Foundation',
              state: 'PLAN_SAVED',
            },
          ],
        }),
      getDraft: () => of(mockDraft),
      saveDraft: () => of(mockDraft),
      acceptArchitecture: () => of(mockAcceptResult),
      stageFoundation: () => {
        staged = true;
        return of(mockStageResult);
      },
    };

    TestBed.configureTestingModule({
      imports: [StackWizardPage],
      providers: [
        provideRouter([]),
        {
          provide: SessionState,
          useValue: {
            session: () => ({
              access: {
                capabilities: [
                  'knowledge.write',
                  'knowledge.approve',
                  'changeset.stage',
                  'access.propose',
                  'rules.manage',
                ],
              },
            }),
          },
        },
        { provide: StackWizardApi, useValue: mockApi },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: (k: string) => (k === 'projectId' ? 'test-project' : null),
              },
              queryParamMap: {
                get: () => null,
              },
            },
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(StackWizardPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    return { fixture, component, mockApi };
  }

  it('initializes with source analysis and presets', () => {
    const { component } = setup();
    expect(component.projectId()).toBe('test-project');
    expect(component.activeStep()).toBe('inventory');
    expect(component.analysis()?.source_framework).toBe('ember-classic');
    expect(component.presets().length).toBe(1);
    expect(component.selectedPresetId()).toBe('angular-17-lts-bootstrap5');
  });

  it('navigates between wizard steps', () => {
    const { component } = setup();
    expect(component.activeStep()).toBe('inventory');

    component.setActiveStep('preset');
    expect(component.activeStep()).toBe('preset');

    component.setActiveStep('matrix');
    expect(component.activeStep()).toBe('matrix');
    expect(component.filteredMappings().length).toBe(1);
    expect(component.filteredMappings()[0]?.legacy_package).toBe('bootstrap');

    component.setActiveStep('adr');
    expect(component.activeStep()).toBe('adr');
    expect(component.adrList().length).toBe(3);
  });

  it('accepts architecture decisions and updates status', () => {
    const { component } = setup();
    component.setActiveStep('adr');

    component.acceptArchitecture();
    expect(component.successMessage()).toContain('ADR-001');
    expect(component.activeStep()).toBe('foundation');
  });

  it('stages foundation workspace files', () => {
    const { component } = setup();
    component.setActiveStep('foundation');

    component.foundationPlanId.set('plan-foundation');
    component.foundationStepId.set('step-foundation');
    component.stageFoundation();
    expect(component.stageResult()?.file_count).toBe(5);
    expect(component.isFoundationStaged()).toBe(true);
    expect(component.successMessage()).toContain('5 files');
  });

  it('keeps a pending architecture signature at its owner handoff', () => {
    const { component, mockApi, fixture } = setup();
    mockApi.acceptArchitecture = () =>
      of({
        ...mockAcceptResult,
        status: 'approval_required',
        review_command: ['agent', 'access', 'approve', 'C:\\source with spaces'],
      });
    component.setActiveStep('adr');
    component.acceptArchitecture();
    fixture.detectChanges();
    expect(component.activeStep()).toBe('adr');
    expect(component.isArchitectureAccepted()).toBe(false);
    expect(component.architectureCommand()).toContain("'C:\\source with spaces'");
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Copy terminal command');
  });
});
