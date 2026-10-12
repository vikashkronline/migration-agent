import type { AccessDecision } from './access/access.models';

export type NodeKind = 'project' | 'group' | 'task' | 'reference';
export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
export type ActionKind = 'stage' | 'validate' | 'apply';
export type ItemSection =
  | 'summary'
  | 'steps'
  | 'checks'
  | 'artifacts'
  | 'activity'
  | 'decision'
  | 'ask';

export interface WorkNode {
  readonly node_id: string;
  readonly parent_id: string | null;
  readonly label: string;
  readonly kind: NodeKind;
  readonly status: string;
  readonly status_tone?: StatusTone;
  readonly dependencies: readonly string[];
  readonly child_count: number;
  readonly complete_count: number;
  readonly task_count: number;
  readonly needs_attention: boolean;
  readonly run_id: string | null;
}

export interface NodePage {
  readonly schema_version?: 1;
  readonly project_id: string;
  readonly revision: string;
  readonly cursor: number;
  readonly nodes: readonly WorkNode[];
  readonly ancestors: readonly WorkNode[];
  readonly total: number;
  readonly next_offset: number | null;
  readonly warnings?: readonly string[];
}

export interface WorkAction {
  readonly kind: ActionKind;
  readonly label: string;
  readonly available: boolean;
  readonly reason: string;
}

export interface WorkDetail {
  readonly schema_version?: 1;
  readonly project_id: string;
  readonly revision: string;
  readonly node: WorkNode;
  readonly summary: string;
  readonly run_id: string | null;
  readonly changeset_id: string | null;
  readonly changeset_digest: string | null;
  readonly base_revision: string | null;
  readonly policy_digest: string | null;
  readonly validation_digest: string | null;
  readonly evidence: readonly (readonly [string, string])[];
  readonly files: readonly string[];
  readonly diff: string;
  readonly review_command: readonly string[];
  readonly ask_command?: readonly string[];
  readonly actions: readonly WorkAction[];
  readonly activity: readonly (readonly [string, string])[];
  readonly diagram: string;
  readonly images: readonly {
    readonly index: number;
    readonly label: string;
    readonly digest: string;
  }[];
  readonly milestones: readonly (readonly [string, string])[];
  readonly owner?: string;
  readonly acceptance?: readonly string[];
  readonly provenance?: string;
  readonly recovery_note?: string;
  readonly destination?: { readonly root: string; readonly fingerprint: string } | null;
}

export interface Session {
  readonly access?: AccessDecision;
  readonly project_id: string;
  readonly actor: string;
  readonly assurance: string;
}
export interface WorkEvents {
  readonly project_id: string;
  readonly cursor: number;
  readonly changed: boolean;
  readonly more: boolean;
}
export interface Receipt {
  readonly operation_id: string;
  readonly status: string;
  readonly message: string;
}
export interface Health {
  readonly status: string;
  readonly checks: readonly {
    readonly name: string;
    readonly status: string;
    readonly details: Readonly<Record<string, unknown>>;
  }[];
}
export interface ImageContent {
  readonly mime_type: 'image/png';
  readonly data: string;
}

export interface Selection {
  readonly nodeId: string;
  readonly artifact: string | null;
  readonly run: string | null;
}

export interface DiffLine {
  readonly kind: 'context' | 'remove' | 'add';
  readonly old_line: number | null;
  readonly new_line: number | null;
  readonly text: string;
}
export interface DiffHunk {
  readonly old_start: number;
  readonly old_count: number;
  readonly new_start: number;
  readonly new_count: number;
  readonly lines: readonly DiffLine[];
}
export interface WorkFileDiff {
  readonly project_id: string;
  readonly node_id: string;
  readonly revision: string;
  readonly changeset_digest: string;
  readonly base_revision: string;
  readonly path: string;
  readonly operation: 'CREATE' | 'MODIFY' | 'DELETE';
  readonly file_mode: string;
  readonly available: boolean;
  readonly reason: string;
  readonly hunks: readonly DiffHunk[];
}
export interface WorkCommand {
  readonly project_id: string;
  readonly node_id: string;
  readonly expected_revision: string;
  readonly request_id: string;
  readonly kind: ActionKind;
  readonly changeset_id: string | null;
}
export interface WorkQuestion {
  readonly project_id: string;
  readonly node_id: string;
  readonly revision: string;
  readonly question: string;
}
export interface WorkAnswer {
  readonly project_id: string;
  readonly node_id: string;
  readonly revision: string;
  readonly mode: 'recorded_evidence';
  readonly answer: string;
  readonly citations: readonly {
    readonly label: string;
    readonly text: string;
    readonly node_id: string;
  }[];
}
