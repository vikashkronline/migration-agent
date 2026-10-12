import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { catchError, map, throwError, timeout } from 'rxjs';
import { apiError } from '../../core/api/api-error';
import type {
  AcceptArchitectureResult,
  PackageMappingOutcome,
  PresetsResult,
  ProjectStackStatus,
  StackAnalysisResult,
  StackRecommendationDraft,
  StageFoundationResult,
  PresetDto,
  DependencyDto,
  DraftDto,
  AnalysisDto,
  TargetStackPreset,
  LegacyDependency,
  ReplacementStrategy,
} from './stack-wizard.models';

interface Envelope<T> {
  readonly status: 'ok' | 'error';
  readonly data?: T;
  readonly error?: {
    readonly code: string;
    readonly message: string;
    readonly details?: unknown;
  };
}

@Injectable({ providedIn: 'root' })
export class StackWizardApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  getPresets(): Observable<PresetsResult> {
    return this.unwrap(
      this.http.get<
        Envelope<{ readonly presets: readonly PresetDto[]; readonly default_preset_id: string }>
      >(`${this.base}/stack/presets`),
    ).pipe(map((res) => ({ ...res, presets: res.presets.map(presetView) })));
  }

  getAnalysis(projectId: string): Observable<StackAnalysisResult> {
    return this.unwrap(
      this.http.get<Envelope<AnalysisDto>>(
        `${this.base}/projects/${encodeURIComponent(projectId)}/stack/analysis`,
      ),
    ).pipe(
      map((res) => ({
        ...res,
        dependencies: res.dependencies.map(dependencyView),
        unmapped_dependencies: res.unmapped_dependencies.map(dependencyView),
        detected_presets: res.detected_presets.map(presetView),
      })),
    );
  }

  getStatus(projectId: string): Observable<ProjectStackStatus> {
    return this.unwrap(
      this.http.get<Envelope<ProjectStackStatus>>(
        `${this.base}/projects/${encodeURIComponent(projectId)}/stack/status`,
      ),
    );
  }

  getDraft(projectId: string): Observable<StackRecommendationDraft> {
    return this.unwrap(
      this.http.get<Envelope<DraftDto>>(
        `${this.base}/projects/${encodeURIComponent(projectId)}/stack/draft`,
      ),
    ).pipe(map(draftView));
  }

  saveDraft(
    projectId: string,
    payload: {
      readonly preset_id?: string;
      readonly custom_mappings?: Readonly<
        Record<string, PackageMappingOutcome | ReplacementStrategy>
      >;
      readonly request_id?: string;
    },
  ): Observable<StackRecommendationDraft> {
    return this.unwrap(
      this.http.post<Envelope<DraftDto>>(
        `${this.base}/projects/${encodeURIComponent(projectId)}/stack/draft`,
        payload,
      ),
    ).pipe(map(draftView));
  }

  acceptArchitecture(
    projectId: string,
    expectedDraftDigest?: string,
  ): Observable<AcceptArchitectureResult> {
    const payload = expectedDraftDigest ? { expected_draft_digest: expectedDraftDigest } : {};
    return this.unwrap(
      this.http.post<Envelope<AcceptArchitectureResult>>(
        `${this.base}/projects/${encodeURIComponent(projectId)}/stack/accept-architecture`,
        payload,
      ),
    );
  }

  stageFoundation(
    projectId: string,
    payload: {
      readonly plan_id: string;
      readonly step_id: string;
      readonly request_id?: string;
    },
  ): Observable<StageFoundationResult> {
    return this.unwrap(
      this.http.post<Envelope<StageFoundationResult>>(
        `${this.base}/projects/${encodeURIComponent(projectId)}/stack/stage-foundation`,
        payload,
      ),
    );
  }

  private unwrap<T>(source: Observable<Envelope<T>>): Observable<T> {
    return source.pipe(
      timeout({ first: 15000 }),
      map((response) => {
        if (response.status !== 'ok' || response.data === undefined || response.data === null) {
          const message = response.error?.message || 'Incompatible stack service response.';
          throw new Error(message);
        }
        return response.data;
      }),
      catchError((error: unknown) => throwError(() => apiError(error))),
    );
  }
}

function presetView(p: PresetDto): TargetStackPreset {
  return {
    preset_id: p.preset_id,
    display_name: p.label,
    description: p.description,
    framework: p.target_framework,
    framework_version: p.angular_version,
    ui_library: p.ui_library,
    state_management: `RxJS ${p.rxjs_version}`,
    build_tool: `TypeScript ${p.typescript_version}`,
    test_runner: p.test_framework,
    compatibility_level: 'Requires project validation',
  };
}
function dependencyView(d: DependencyDto): LegacyDependency {
  return {
    name: d.name,
    version_spec: d.declared_version,
    category: d.category,
    is_dev: d.is_dev,
    detected_in: d.manifest_path,
    evidence_locations: d.usage_evidence,
  };
}
function draftView(d: DraftDto): StackRecommendationDraft {
  return {
    draft_id: d.draft_id,
    project_id: d.project_id,
    preset_id: d.preset.preset_id,
    content_digest: d.content_digest,
    status: 'draft',
    decisions: d.decisions ?? [],
    custom_mappings: Object.fromEntries(
      d.mappings.map((m) => [
        m.legacy_name,
        {
          legacy_package: m.legacy_name,
          strategy: m.strategy,
          description: m.rationale,
          rationale: m.rationale,
          confidence: null,
          suggested_alternatives: [],
          target_packages: m.target_packages.map((p) => ({
            package_name: p.name,
            version_range: p.version_spec,
          })),
        },
      ]),
    ),
  };
}
