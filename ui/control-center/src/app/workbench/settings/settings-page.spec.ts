import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { SessionState } from '../../core/session/session-state';
import { SettingsPage } from './settings-page';
import type { ConfigurationView, LocalConfiguration } from './settings.models';

const local: LocalConfiguration = {
  schema_version: 1,
  profile_id: null,
  model: null,
  max_turns: null,
  validation_mode: null,
  native_toolchain_root: null,
  native_dependencies_root: null,
  native_browser_path: null,
  browser_validation_plan: null,
  validation_image: null,
  final_target_root: null,
  next_state_dir: null,
  next_staging_root: null,
};
const view: ConfigurationView = {
  project_id: 'bound',
  revision: 'r1',
  access_digest: 'a1',
  principal_id: 'user',
  capabilities: [
    'project.read',
    'configuration.read',
    'configuration.local.write',
    'configuration.propose',
    'provider.use',
  ],
  is_owner: false,
  project: {
    schema_version: 1,
    profiles: [
      {
        profile_id: 'allowed',
        provider: 'gemini',
        models: ['model-a', 'model-b'],
        default_model: 'model-a',
        allowed_payloads: ['connectivity'],
      },
    ],
    default_profile: 'allowed',
    max_turns: 10,
    max_step_files: 10,
    allowed_validation_modes: ['restricted'],
    browser_provider_export: false,
    target_preset_id: null,
  },
  local,
  effective: { fields: [], diagnostics: [] },
  bindings: { source_root: '/source' },
  field_descriptors: [],
  restart_arguments: [],
};

describe('Settings request recovery and separate scopes', () => {
  let http: HttpTestingController;
  let component: SettingsPage;
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [SettingsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: SessionState, useValue: { require: () => ({ project_id: 'bound' }) } },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(convertToParamMap({ section: 'models' })) },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    component = TestBed.createComponent(SettingsPage).componentInstance;
    http
      .expectOne('/api/v1/projects/bound/configuration')
      .flush({ status: 'ok', data: structuredClone(view) });
  });
  afterEach(() => {
    http.verify();
    TestBed.resetTestingModule();
  });

  it('replays the exact provider check rather than changing its kind after a lost response', () => {
    component.runCheck('provider');
    expect(component.confirmation()).toBe('provider');
    component.confirmProbe();
    const first = http.expectOne('/api/v1/projects/bound/configuration/checks');
    const original: unknown = first.request.body;
    first.error(new ProgressEvent('error'));
    expect(component.outcomeUnknown()).toBe(true);
    component.retryUnknown();
    const replay = http.expectOne('/api/v1/projects/bound/configuration/checks');
    expect(replay.request.body).toEqual(original);
    expect((replay.request.body as { kind: string }).kind).toBe('provider');
    replay.flush({
      status: 'ok',
      data: { operation_id: 'op-1', status: 'QUEUED', diagnostics: [], input_revision: 'r1' },
    });
  });

  it('retains shared edits when a personal selection is saved', () => {
    component.changeProject('max_turns', 7);
    component.changeLocal('model', 'model-b');
    component.saveLocal();
    http.expectOne('/api/v1/projects/bound/configuration/local').flush({
      status: 'ok',
      data: { status: 'SAVED', request_id: 'recorded', revision: 'r2', message: 'Saved' },
    });
    http.expectOne('/api/v1/projects/bound/configuration').flush({
      status: 'ok',
      data: { ...view, revision: 'r2', local: { ...local, model: 'model-b' } },
    });
    expect(component.projectDraft()?.max_turns).toBe(7);
    expect(component.projectDirty()).toBe(true);
    expect(component.localDirty()).toBe(false);
    expect(component.stale()).toBe(false);
  });

  it('preserves edits and blocks a new write after a stale revision response', () => {
    component.changeLocal('max_turns', 5);
    component.saveLocal();
    http
      .expectOne('/api/v1/projects/bound/configuration/local')
      .flush(
        { status: 'error', error: { code: 'CONFLICT', message: 'CONFIGURATION_STALE: refresh.' } },
        { status: 409, statusText: 'Conflict' },
      );
    expect(component.localDraft()?.max_turns).toBe(5);
    expect(component.outcomeUnknown()).toBe(false);
  });

  it('asks before discarding an unsaved draft when leaving Settings', async () => {
    component.changeProject('max_turns', 6);
    const leaving = component.canLeave();
    expect(component.leavePrompt()).toBe(true);
    component.finishLeave(false);
    expect(await leaving).toBe(false);
    expect(component.projectDraft()?.max_turns).toBe(6);
  });

  it('does not treat read access as permission to change settings', () => {
    component.view.set({ ...view, capabilities: ['project.read', 'configuration.read'] });
    expect(component.canLocal()).toBe(false);
    expect(component.canPropose()).toBe(false);
    component.saveLocal();
    http.expectNone('/api/v1/projects/bound/configuration/local');
  });
});
