import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { catchError, filter, of, switchMap } from 'rxjs';
import { CcIcon, type IconName } from '../../../shared/icon/cc-icon';
import { StatusBadge } from '../../../shared/status-badge/status-badge';
import { WorkbenchStore } from '../../workbench-store';
import { WorkbenchApi } from '../../workbench-api';
import { DiagramPreview } from '../../references/diagram-preview';
import type { WorkNode } from '../../workbench.models';
import { StackWizardApi } from '../../wizard/stack-wizard-api';
import type { ProjectStackStatus } from '../../wizard/stack-wizard.models';

export interface Recommendation {
  readonly type: 'architecture' | 'foundation' | 'prerequisite' | 'attention' | 'next';
  readonly targetNodeId: string;
  readonly targetLabel: string;
  readonly badgeLabel: string;
  readonly icon: IconName;
  readonly message: string;
  readonly actionLabel: string;
  readonly targetRoute?: readonly unknown[];
}

@Component({
  selector: 'cc-summary-page',
  imports: [RouterLink, StatusBadge, DiagramPreview, CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './summary-page.html',
})
export class SummaryPage {
  protected readonly store = inject(WorkbenchStore);
  private readonly api = inject(WorkbenchApi);
  private readonly stackApi = inject(StackWizardApi);
  private readonly destroyRef = inject(DestroyRef);
  private readonly projectTasks = signal<readonly WorkNode[]>([]);
  protected readonly stackStatus = signal<ProjectStackStatus | null>(null);

  constructor() {
    toObservable(this.store.detail)
      .pipe(
        filter((d): d is NonNullable<typeof d> => d !== null && d.node.kind !== 'task'),
        switchMap((d) =>
          this.api.tree({ project: d.project_id, kind: 'task' }).pipe(catchError(() => of(null))),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((page) => {
        if (page) {
          this.projectTasks.set(page.nodes.filter((n) => n.kind === 'task'));
        }
      });

    toObservable(this.store.detail)
      .pipe(
        filter((d): d is NonNullable<typeof d> => d !== null),
        switchMap((d) => this.stackApi.getStatus(d.project_id).pipe(catchError(() => of(null)))),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((status) => {
        if (status) {
          this.stackStatus.set(status);
        }
      });
  }

  protected readonly cards = computed(() => {
    const detail = this.store.detail();
    if (!detail) return [];
    const directChildren = this.store.children().get(detail.node.node_id) ?? [];
    if (directChildren.length > 0) return directChildren;
    if (detail.node.node_id === 'project') {
      return (this.store.children().get(null) ?? []).filter((c) => c.node_id !== 'project');
    }
    return [];
  });

  protected readonly nextRecommendedTask = computed<Recommendation | null>(() => {
    const detail = this.store.detail();
    if (!detail) return null;
    const allNodes = this.store.nodes();
    const status = this.stackStatus();

    // STAGE 1: Architecture & Knowledge Precedence
    // Authoritative backend status has precedence over heuristic tree counts
    if (status && !status.architecture_accepted) {
      return {
        type: 'architecture',
        targetNodeId: 'wizard/foundation',
        targetLabel: 'Target Stack & Architecture Selection',
        badgeLabel: 'Architecture Decisions Required',
        icon: 'journal-bookmark',
        message:
          'No architectural decisions (ADRs) or target framework standards are recorded. Establish architecture decisions before starting functional migration.',
        actionLabel: 'Open Stack & Foundation Wizard',
        targetRoute: ['/projects', detail.project_id, 'wizard', 'foundation'],
      };
    }

    const knowledgeNode = allNodes.find((n) => n.node_id === 'knowledge');
    const references = allNodes.filter(
      (n) => n.parent_id === 'knowledge' || n.kind === 'reference',
    );
    const archCount = (knowledgeNode?.child_count ?? 0) + references.length;
    if (!status && archCount === 0) {
      return {
        type: 'architecture',
        targetNodeId: 'knowledge',
        targetLabel: '3. Architecture & knowledge',
        badgeLabel: 'Architecture Decisions Required',
        icon: 'journal-bookmark',
        message:
          'No architectural decisions (ADRs) or target framework standards are recorded. Establish architecture decisions before starting functional migration.',
        actionLabel: 'Open Architecture & Knowledge',
        targetRoute: ['/projects', detail.project_id, 'wizard', 'foundation'],
      };
    }

    // STAGE 2: Foundation & Readiness Precedence
    // If backend reports foundation not staged, recommend foundation staging wizard
    if (status && !status.foundation_staged) {
      return {
        type: 'foundation',
        targetNodeId: 'wizard/foundation',
        targetLabel: 'Foundation Workspace Initialization',
        badgeLabel: 'Foundation Readiness Required',
        icon: 'shield-check',
        message:
          'Baseline target foundation workspace (step-001) must be staged before functional component migration.',
        actionLabel: 'Stage Foundation Workspace',
        targetRoute: ['/projects', detail.project_id, 'wizard', 'foundation'],
      };
    }

    // If Foundation has declared tasks in the tree, all must be verified and applied first
    const foundationTasks = allNodes.filter(
      (n) => n.parent_id === 'foundation' && n.kind === 'task',
    );
    const uncompletedFoundation = foundationTasks.filter((n) => n.status !== 'APPLY_COMPLETED');
    const nextFound = uncompletedFoundation[0];
    if (nextFound) {
      return {
        type: 'foundation',
        targetNodeId: nextFound.node_id,
        targetLabel: nextFound.label,
        badgeLabel: 'Foundation Readiness Required',
        icon: 'shield-check',
        message: `Baseline platform foundation task "${nextFound.label}" must be verified and applied before functional component migration.`,
        actionLabel: `Go to ${nextFound.label}`,
      };
    }

    // STAGE 3: Workflows & Topological Dependency Precedence
    const fetchedTasks = this.projectTasks();
    const storeTasks = allNodes.filter((n) => n.kind === 'task');
    const allTasks = fetchedTasks.length > 0 ? fetchedTasks : storeTasks;
    if (allTasks.length === 0) return null;

    const nodeMap = new Map<string, WorkNode>(
      [...allNodes, ...fetchedTasks].map((n) => [n.node_id, n]),
    );

    // Check attention tasks first, but RESPECT topological dependencies!
    const attentionTask = allTasks.find((n) => n.needs_attention);
    if (attentionTask) {
      const unappliedPrereqs = (attentionTask.dependencies || [])
        .map((depId) => nodeMap.get(depId))
        .filter((dep): dep is WorkNode => !!dep && dep.status !== 'APPLY_COMPLETED');

      const rootPrereq = unappliedPrereqs[0];
      if (rootPrereq) {
        // The task needing attention is blocked by unapplied prerequisites!
        return {
          type: 'prerequisite',
          targetNodeId: rootPrereq.node_id,
          targetLabel: rootPrereq.label,
          badgeLabel: 'Prerequisite Required',
          icon: 'lock',
          message: `Task "${attentionTask.label}" is blocked because prerequisite "${rootPrereq.label}" has not been applied. Complete and apply prerequisites first.`,
          actionLabel: `Go to ${rootPrereq.label}`,
        };
      }

      // Attention task has all prerequisites applied, so it genuinely needs attention now:
      return {
        type: 'attention',
        targetNodeId: attentionTask.node_id,
        targetLabel: attentionTask.label,
        badgeLabel: 'Attention Required',
        icon: 'exclamation-triangle-fill',
        message: `Task "${attentionTask.label}" requires attention (${attentionTask.status}). Inspect checks, diff, and activity.`,
        actionLabel: `Go to ${attentionTask.label}`,
      };
    }

    // No attention task: find the next task in topological order whose prerequisites are satisfied:
    const nextTask = allTasks.find((task) => {
      if (task.status === 'APPLY_COMPLETED') return false;
      const unappliedPrereqs = (task.dependencies || [])
        .map((depId) => nodeMap.get(depId))
        .filter((dep): dep is WorkNode => !!dep && dep.status !== 'APPLY_COMPLETED');
      return unappliedPrereqs.length === 0;
    });

    if (nextTask) {
      const hint =
        nextTask.status === 'APPROVAL_RECORDED'
          ? 'Exact human approval recorded. Ready to apply artifact.'
          : nextTask.status === 'VALIDATION_PASSED'
            ? 'Validation passed. Review artifact in trusted terminal to record approval.'
            : nextTask.status === 'STAGE_VERIFIED'
              ? 'Proposal staged. Proceed with required validation.'
              : nextTask.status === 'PLANNED'
                ? 'Task planned. Proceed to stage proposal.'
                : `Task in progress (${nextTask.status}).`;
      return {
        type: 'next',
        targetNodeId: nextTask.node_id,
        targetLabel: nextTask.label,
        badgeLabel: 'Recommended Next Step',
        icon: 'hourglass-split',
        message: hint,
        actionLabel: `Go to ${nextTask.label}`,
      };
    }

    return null;
  });

  protected readonly unappliedDependencies = computed(() => {
    const detail = this.store.detail();
    if (!detail || detail.node.kind !== 'task') return [];
    return detail.node.dependencies
      .map((id) => this.store.node(id))
      .filter((n): n is NonNullable<typeof n> => !!n && n.status !== 'APPLY_COMPLETED');
  });

  protected getNodeIcon(node: WorkNode): IconName {
    if (node.kind === 'project') return 'folder2';
    if (node.node_id === 'foundation') return 'shield-check';
    if (node.node_id === 'work') return 'diagram-3';
    if (node.node_id === 'knowledge') return 'journal-bookmark';
    if (node.kind === 'reference') return 'file-earmark-text';
    if (node.kind === 'task') return 'collection';
    if (node.kind === 'group') return 'collection';
    return 'folder2';
  }
}
