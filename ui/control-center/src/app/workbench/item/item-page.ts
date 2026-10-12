import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  afterNextRender,
  computed,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  ActivatedRoute,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { combineLatest, distinctUntilChanged, map } from 'rxjs';
import { CcIcon, type IconName } from '../../shared/icon/cc-icon';
import { Feedback } from '../../shared/feedback/feedback';
import { StatusBadge } from '../../shared/status-badge/status-badge';
import { WorkflowActions } from '../actions/workflow-actions';
import { WorkbenchStore } from '../workbench-store';
import type { WorkNode } from '../workbench.models';

interface TabItem {
  readonly path: string;
  readonly label: string;
  readonly icon: IconName;
}

@Component({
  selector: 'cc-item-page',
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    StatusBadge,
    Feedback,
    WorkflowActions,
    CcIcon,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './item-page.html',
})
export class ItemPage {
  protected readonly store = inject(WorkbenchStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly document = inject(DOCUMENT);
  protected readonly tabs = computed<readonly TabItem[]>(() => {
    const kind = this.store.detail()?.node.kind;
    if (kind === 'task') {
      return [
        { path: 'summary', label: 'Summary', icon: 'speedometer2' },
        { path: 'steps', label: 'Steps', icon: 'collection' },
        { path: 'checks', label: 'Checks', icon: 'clipboard-check' },
        { path: 'artifacts', label: 'Artifacts', icon: 'file-diff' },
        { path: 'activity', label: 'Activity', icon: 'clock-history' },
        { path: 'decision', label: 'Decision', icon: 'shield-lock' },
        { path: 'ask', label: 'Ask', icon: 'chat-dots' },
      ];
    }
    if (kind === 'reference') {
      return [
        { path: 'summary', label: 'Summary', icon: 'speedometer2' },
        { path: 'ask', label: 'Ask', icon: 'chat-dots' },
      ];
    }
    return [
      { path: 'summary', label: 'Summary', icon: 'speedometer2' },
      { path: 'activity', label: 'Activity', icon: 'clock-history' },
      { path: 'ask', label: 'Ask', icon: 'chat-dots' },
    ];
  });
  protected readonly currentLink = computed(() => [
    '/projects',
    this.store.detail()?.project_id ?? '',
    'items',
    this.store.detail()?.node.node_id ?? '',
  ]);

  constructor() {
    combineLatest([this.route.paramMap, this.route.queryParamMap])
      .pipe(
        map(([params, query]) => ({
          nodeId: params.get('nodeId') ?? 'project',
          artifact: query.get('artifact'),
          run: query.get('run'),
        })),
        distinctUntilChanged(
          (a, b) => a.nodeId === b.nodeId && a.artifact === b.artifact && a.run === b.run,
        ),
        takeUntilDestroyed(),
      )
      .subscribe((selection) => {
        this.store.select(selection);
      });

    afterNextRender(() => {
      this.document.getElementById('content-heading')?.focus();
    });
  }

  protected getNodeIcon(node: WorkNode): IconName {
    if (node.kind === 'project') return 'folder2';
    if (node.node_id === 'foundation') return 'shield-check';
    if (node.node_id === 'work') return 'diagram-3';
    if (node.node_id === 'knowledge') return 'journal-bookmark';
    if (node.kind === 'reference') return 'file-earmark-text';
    if (node.kind === 'task') return 'collection';
    return 'folder2';
  }

  protected openCurrent(): void {
    const detail = this.store.detail();
    if (!detail) {
      this.store.select({ nodeId: 'project', artifact: null, run: null });
      return;
    }
    void this.router.navigate(this.currentLink(), { queryParamsHandling: 'preserve' });
  }
}
