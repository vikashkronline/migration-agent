import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { StackWizardApi } from './stack-wizard-api';

describe('StackWizardApi HTTP client', () => {
  let api: StackWizardApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), StackWizardApi],
    });
    api = TestBed.inject(StackWizardApi);
    http = TestBed.inject(HttpTestingController);
  });

  it('fetches target stack presets', () => {
    api.getPresets().subscribe((res) => {
      expect(res.presets.length).toBe(1);
      expect(res.default_preset_id).toBe('angular-17-lts-bootstrap5');
    });

    const req = http.expectOne('/api/v1/stack/presets');
    expect(req.request.method).toBe('GET');
    req.flush({
      status: 'ok',
      data: {
        presets: [
          {
            preset_id: 'angular-17-lts-bootstrap5',
            label: 'Angular 17 LTS',
            description: 'Modern baseline',
            target_framework: 'angular',
            angular_version: '17.3.12',
            ui_library: 'bootstrap-5.3',
            state_management: 'signals',
            build_tool: 'angular-build',
            test_framework: 'vitest',
            compatibility_level: 'high',
          },
        ],
        default_preset_id: 'angular-17-lts-bootstrap5',
      },
    });
    http.verify();
  });

  it('fetches source analysis for a project', () => {
    api.getAnalysis('proj-1').subscribe((res) => {
      expect(res.project_id).toBe('proj-1');
      expect(res.source_framework).toBe('ember-classic');
      expect(res.dependencies.length).toBe(1);
    });

    const req = http.expectOne('/api/v1/projects/proj-1/stack/analysis');
    expect(req.request.method).toBe('GET');
    req.flush({
      status: 'ok',
      data: {
        project_id: 'proj-1',
        source_framework: 'ember-classic',
        dependencies: [
          {
            name: 'ember-source',
            declared_version: '~3.28.0',
            category: 'framework',
            is_dev: false,
            manifest_path: 'package.json',
            usage_evidence: ['package.json'],
          },
        ],
        existing_adrs: [],
        detected_presets: [],
        unmapped_dependencies: [],
        readiness_status: {
          ready: false,
          architecture_accepted: false,
          foundation_staged: false,
          accepted_decision_ids: [],
        },
      },
    });
    http.verify();
  });

  it('saves working draft and accepts architecture decisions', () => {
    api.saveDraft('proj-1', { preset_id: 'angular-17-lts-bootstrap5' }).subscribe((draft) => {
      expect(draft.draft_id).toBe('draft-1');
      expect(draft.preset_id).toBe('angular-17-lts-bootstrap5');
    });

    const draftReq = http.expectOne('/api/v1/projects/proj-1/stack/draft');
    expect(draftReq.request.method).toBe('POST');
    draftReq.flush({
      status: 'ok',
      data: {
        draft_id: 'draft-1',
        project_id: 'proj-1',
        preset: { preset_id: 'angular-17-lts-bootstrap5' },
        mappings: [],
        content_digest: 'abc123digest',
        status: 'draft',
      },
    });

    api.acceptArchitecture('proj-1', 'abc123digest').subscribe((res) => {
      expect(res.status).toBe('accepted');
      expect(res.accepted_decision_ids).toContain('ADR-001');
    });

    const acceptReq = http.expectOne('/api/v1/projects/proj-1/stack/accept-architecture');
    expect(acceptReq.request.method).toBe('POST');
    expect(acceptReq.request.body).toEqual({ expected_draft_digest: 'abc123digest' });
    acceptReq.flush({
      status: 'ok',
      data: {
        status: 'accepted',
        accepted_adrs: [],
        accepted_decision_ids: ['ADR-001', 'ADR-002', 'ADR-003'],
      },
    });

    http.verify();
  });

  it('stages foundation workspace', () => {
    api
      .stageFoundation('proj-1', { plan_id: 'plan-1', step_id: 'step-1', request_id: 'stage-1' })
      .subscribe((res) => {
        expect(res.status).toBe('staged');
        expect(res.file_count).toBe(5);
      });

    const req = http.expectOne('/api/v1/projects/proj-1/stack/stage-foundation');
    expect(req.request.method).toBe('POST');
    req.flush({
      status: 'ok',
      data: {
        status: 'staged',
        run_id: 'run-1',
        staged_directory: '/staging/run-1',
        file_count: 5,
        files: ['package.json', 'tsconfig.json'],
        changeset_digest: 'digest-xyz',
      },
    });
    http.verify();
  });
});
