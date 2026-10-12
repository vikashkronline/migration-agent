export interface LegacyDependency {
  readonly name: string;
  readonly version_spec: string;
  readonly category: string;
  readonly is_dev: boolean;
  readonly detected_in: string;
  readonly evidence_locations: readonly string[];
}

export interface PackageCoordinate {
  readonly package_name: string;
  readonly version_range: string;
  readonly notes?: string;
}

export type ReplacementStrategy = 'replace' | 'native' | 'remove' | 'keep' | 'custom' | 'deferred';

export interface PackageMappingOutcome {
  readonly legacy_package: string;
  readonly target_packages: readonly PackageCoordinate[];
  readonly strategy: ReplacementStrategy;
  readonly description: string;
  readonly suggested_alternatives: readonly string[];
  readonly confidence: number | null;
  readonly rationale?: string;
}

export interface TargetStackPreset {
  readonly preset_id: string;
  readonly display_name: string;
  readonly description: string;
  readonly framework: string;
  readonly framework_version: string;
  readonly ui_library: string;
  readonly state_management: string;
  readonly build_tool: string;
  readonly test_runner: string;
  readonly compatibility_level: string;
}

export interface ArchitecturalDecisionRecord {
  readonly decision_id: string;
  readonly title: string;
  readonly status: string;
  readonly context: string;
  readonly decision: string;
  readonly consequences: string;
  readonly decided_by?: string;
  readonly decided_at?: string;
  readonly epistemic_status?: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface ReadinessStatus {
  readonly ready: boolean;
  readonly architecture_accepted: boolean;
  readonly foundation_staged: boolean;
  readonly accepted_decision_ids: readonly string[];
  readonly ready_for_migration?: boolean;
}

export interface StackAnalysisResult {
  readonly project_id: string;
  readonly source_framework: string;
  readonly dependencies: readonly LegacyDependency[];
  readonly existing_adrs: readonly ArchitecturalDecisionRecord[];
  readonly detected_presets: readonly TargetStackPreset[];
  readonly unmapped_dependencies: readonly LegacyDependency[];
  readonly readiness_status: ReadinessStatus;
}

export interface StackRecommendationDraft {
  readonly draft_id: string;
  readonly project_id: string;
  readonly preset_id: string;
  readonly custom_mappings: Readonly<Record<string, PackageMappingOutcome>>;
  readonly decisions: readonly ArchitecturalDecisionRecord[];
  readonly content_digest: string;
  readonly status: string;
}

export interface AcceptArchitectureResult {
  readonly status: string;
  readonly accepted_adrs: readonly ArchitecturalDecisionRecord[];
  readonly accepted_decision_ids: readonly string[];
  readonly proposal_id?: string;
  readonly signing_digest?: string;
  readonly review_command?: readonly string[];
}

export interface StageFoundationResult {
  readonly status: string;
  readonly run_id: string;
  readonly staged_directory: string;
  readonly file_count: number;
  readonly files: readonly string[];
  readonly changeset_digest: string;
}

export interface PresetsResult {
  readonly presets: readonly TargetStackPreset[];
  readonly default_preset_id: string;
}

export interface ProjectStackStatus {
  readonly project_id: string;
  readonly architecture_accepted: boolean;
  readonly foundation_staged: boolean;
  readonly accepted_decision_ids: readonly string[];
  readonly ready_for_migration: boolean;
  readonly foundation_validated?: boolean;
  readonly foundation_published?: boolean;
  readonly target_root?: string | null;
  readonly foundation_tasks?: readonly {
    readonly plan_id: string;
    readonly step_id: string;
    readonly title: string;
    readonly state: string;
  }[];
}

export interface PresetDto {
  readonly preset_id: string;
  readonly label: string;
  readonly description: string;
  readonly target_framework: string;
  readonly angular_version: string;
  readonly ui_library: string;
  readonly typescript_version: string;
  readonly rxjs_version: string;
  readonly test_framework: string;
}
export interface DependencyDto {
  readonly name: string;
  readonly declared_version: string;
  readonly category: string;
  readonly is_dev: boolean;
  readonly manifest_path: string;
  readonly usage_evidence: readonly string[];
}
export interface DraftDto {
  readonly decisions?: readonly ArchitecturalDecisionRecord[];
  readonly draft_id: string;
  readonly project_id: string;
  readonly preset: PresetDto;
  readonly mappings: readonly {
    readonly legacy_name: string;
    readonly strategy: ReplacementStrategy;
    readonly rationale: string;
    readonly target_packages: readonly { readonly name: string; readonly version_spec: string }[];
  }[];
  readonly content_digest: string;
}
export interface AnalysisDto {
  readonly project_id: string;
  readonly source_framework: string;
  readonly dependencies: readonly DependencyDto[];
  readonly unmapped_dependencies: readonly DependencyDto[];
  readonly detected_presets: readonly PresetDto[];
  readonly existing_adrs: readonly ArchitecturalDecisionRecord[];
  readonly readiness_status: ReadinessStatus;
}
