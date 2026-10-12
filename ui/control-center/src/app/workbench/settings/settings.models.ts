export type ExecutionMode = 'restricted' | 'native' | 'container';
export interface RuntimeProfile {
  readonly profile_id: string;
  readonly provider: 'gemini' | 'openai';
  readonly models: readonly string[];
  readonly default_model: string;
  readonly allowed_payloads: readonly (
    | 'connectivity'
    | 'source_analysis'
    | 'planning'
    | 'contextual_qa'
    | 'browser_review'
  )[];
}
export interface ProjectConfiguration {
  readonly schema_version: 1;
  readonly profiles: readonly RuntimeProfile[];
  readonly default_profile: string | null;
  readonly max_turns: number;
  readonly max_step_files: number;
  readonly allowed_validation_modes: readonly ExecutionMode[];
  readonly browser_provider_export: boolean;
  readonly target_preset_id: string | null;
}
export interface LocalConfiguration {
  readonly schema_version: 1;
  readonly profile_id: string | null;
  readonly model: string | null;
  readonly max_turns: number | null;
  readonly validation_mode: ExecutionMode | null;
  readonly native_toolchain_root: string | null;
  readonly native_dependencies_root: string | null;
  readonly native_browser_path: string | null;
  readonly browser_validation_plan: string | null;
  readonly validation_image: string | null;
  readonly final_target_root: string | null;
  readonly next_state_dir: string | null;
  readonly next_staging_root: string | null;
}
export interface ConfigurationDiagnostic {
  readonly field: string;
  readonly code: string;
  readonly severity: 'error' | 'prerequisite' | 'warning' | 'info';
  readonly message: string;
  readonly action: string;
}
export interface ConfigurationView {
  readonly project_id: string;
  readonly revision: string;
  readonly access_digest: string;
  readonly principal_id: string;
  readonly capabilities: readonly string[];
  readonly is_owner: boolean;
  readonly project: ProjectConfiguration;
  readonly local: LocalConfiguration;
  readonly effective: {
    readonly fields: readonly {
      readonly name: string;
      readonly value: string | number | boolean | null;
      readonly origin: string;
      readonly scope: string;
      readonly update_mode: string;
    }[];
    readonly diagnostics: readonly ConfigurationDiagnostic[];
  };
  readonly bindings: Readonly<Record<string, string>>;
  readonly field_descriptors: readonly {
    readonly name: string;
    readonly label: string;
    readonly section: string;
    readonly scope: string;
    readonly kind: string;
    readonly help: string;
  }[];
  readonly restart_arguments: readonly string[];
}
export interface ConfigurationReceipt {
  readonly request_id: string;
  readonly status: string;
  readonly revision: string;
  readonly proposal_id: string | null;
  readonly message: string;
}
export interface ConfigurationProposal {
  readonly proposal_id: string;
  readonly project_id: string;
  readonly principal_id: string;
  readonly base_access_digest: string;
  readonly configuration: ProjectConfiguration;
  readonly created_at: string;
  readonly request_id: string;
}
export interface ConfigurationReview {
  readonly proposal: ConfigurationProposal;
  readonly active: ProjectConfiguration;
  readonly diagnostics: readonly ConfigurationDiagnostic[];
  readonly impact: readonly string[];
  readonly signing_digest: string | null;
  readonly access_proposal_id: string | null;
  readonly review_command: readonly string[];
}
export interface ConfigurationCheck {
  readonly operation_id: string;
  readonly request_id: string;
  readonly status: string;
  readonly input_revision: string;
  readonly diagnostics: readonly ConfigurationDiagnostic[];
}
export interface SetupRequest {
  readonly source_root: string;
  readonly governance_root: string;
  readonly state_dir: string;
  readonly staging_root: string;
  readonly project_name: string;
}
export interface SetupPlan {
  readonly request: SetupRequest;
  readonly command_arguments: readonly string[];
  readonly message: string;
}
