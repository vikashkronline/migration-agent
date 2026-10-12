export interface GitAccount {
  readonly provider: 'github' | 'gitlab';
  readonly host: string;
  readonly account_id: string;
  readonly login: string;
}

export interface OnboardingPacket {
  readonly schema_version: 1;
  readonly project_id: string;
  readonly access_digest: string;
  readonly source_root: string;
  readonly source_root_commit: string;
  readonly governance_root: string;
  readonly principal_id: string;
  readonly status: string;
  readonly roles: readonly string[];
  readonly assigned_capabilities: readonly string[];
  readonly key_fingerprint: string | null;
  readonly steps: readonly string[];
}
export interface AccessMember {
  readonly principal_id: string;
  readonly label: string;
  readonly roles: readonly string[];
  readonly status: 'pending' | 'active' | 'suspended';
  readonly os_identity: string | null;
  readonly public_key: string | null;
  readonly key_fingerprint: string | null;
  readonly git_account: GitAccount | null;
  readonly expires_at: number | null;
}
export interface AccessRole {
  readonly role_id: string;
  readonly label: string;
  readonly capabilities: readonly string[];
}
export interface AccessPolicy {
  readonly git_repository: (DirectoryRequest & { readonly repository_id: string }) | null;
  readonly schema_version: 2;
  readonly catalog_version: 1;
  readonly revision: number;
  readonly revision_nonce: string;
  readonly previous_digest: string | null;
  readonly binding: {
    readonly project_id: string;
    readonly source_root: string;
    readonly governance_root: string;
    readonly source_root_commit: string;
    readonly governance_root_commit: string;
  };
  readonly roles: readonly AccessRole[];
  readonly members: readonly AccessMember[];
  readonly owners: readonly string[];
  readonly rules: Readonly<Record<string, string>>;
}
export interface AccessDecision {
  readonly allowed: boolean;
  readonly reason: string;
  readonly principal_id: string | null;
  readonly roles: readonly string[];
  readonly capabilities: readonly string[];
  readonly access_digest: string | null;
}
export interface AccessProposal {
  readonly proposal_id: string;
  readonly candidate: AccessPolicy;
  readonly snapshot_digest: string;
  readonly revision_locator: string;
  readonly base_digest: string | null;
  readonly proposer: string;
  readonly created_at: number;
  readonly expires_at: number;
  readonly nonce: string;
}
export interface AccessReview {
  readonly proposal: AccessProposal;
  readonly before: AccessPolicy | null;
  readonly signing_digest: string;
  readonly review_command: readonly string[];
  readonly approval_channel: 'trusted-terminal';
  readonly message: string;
}
export type AccessMutation =
  | { readonly kind: 'member.set'; readonly member: AccessMember }
  | { readonly kind: 'member.remove'; readonly entity_id: string }
  | { readonly kind: 'role.set'; readonly role: AccessRole }
  | { readonly kind: 'role.remove'; readonly entity_id: string }
  | { readonly kind: 'owners.set'; readonly owners: readonly string[] }
  | {
      readonly kind: 'repository.set';
      readonly repository: DirectoryRequest & { readonly repository_id: string };
    };
export interface DirectoryRequest {
  readonly provider: 'github' | 'gitlab';
  readonly host: string;
  readonly repository: string;
}
export interface DirectoryMember {
  readonly account: GitAccount;
  readonly git_role: string;
  readonly state: 'active' | 'blocked';
  readonly expires_at: string | null;
}
export interface DirectoryResult {
  readonly repository_id: string;
  readonly request: DirectoryRequest;
  readonly members: readonly DirectoryMember[];
  readonly complete: true;
  readonly message: string;
}
