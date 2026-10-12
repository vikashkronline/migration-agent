import { DOCUMENT } from '@angular/common';
import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import type { Observable } from 'rxjs';
import {
  EMPTY,
  Subject,
  catchError,
  debounceTime,
  distinctUntilChanged,
  exhaustMap,
  filter,
  finalize,
  forkJoin,
  map,
  of,
  switchMap,
  tap,
  timer,
} from 'rxjs';
import { ApiError, apiError } from '../core/api/api-error';
import { SessionState } from '../core/session/session-state';
import type { TreeQuery } from './workbench-api';
import { WorkbenchApi } from './workbench-api';
import type {
  ActionKind,
  NodePage,
  Receipt,
  Selection,
  WorkCommand,
  WorkDetail,
  WorkNode,
} from './workbench.models';

export interface ExplorerRow {
  readonly node: WorkNode;
  readonly depth: number;
}
export interface BranchPage {
  readonly next: number | null;
  readonly loading: boolean;
  readonly error: ApiError | null;
}
interface PendingCommand {
  readonly request: WorkCommand;
  readonly label: string;
  readonly outcome: 'pending' | 'unknown' | 'rejected' | 'received';
  readonly receipt: Receipt | null;
}

@Injectable()
export class WorkbenchStore {
  private readonly api = inject(WorkbenchApi);
  private readonly sessionState = inject(SessionState);
  private readonly document = inject(DOCUMENT);
  private readonly destroyRef = inject(DestroyRef);
  private readonly headers = signal<readonly WorkNode[]>([]);
  private readonly currentDetail = signal<WorkDetail | null>(null);
  private readonly currentSelection = signal<Selection>({
    nodeId: 'project',
    artifact: null,
    run: null,
  });
  private readonly expansion = signal<ReadonlySet<string>>(new Set());
  private readonly filterQuery = signal('');
  private readonly attentionOnly = signal(false);
  private readonly connected = signal(false);
  private readonly loadingTree = signal(false);
  private readonly loadingDetail = signal(false);
  private readonly treeFailure = signal<ApiError | null>(null);
  private readonly detailFailure = signal<ApiError | null>(null);
  private readonly branches = signal<ReadonlyMap<string, BranchPage>>(new Map());
  private readonly matches = signal<ReadonlySet<string> | null>(null);
  private readonly matchTotal = signal(0);
  private readonly matchNext = signal<number | null>(null);
  private readonly projectName = signal('Project');
  private readonly revision = signal('');
  private cursor = 0;
  private started = false;
  private readonly refreshRequests = new Subject<void>();
  private readonly selectionRequests = new Subject<Selection>();
  private readonly searchRequests = new Subject<string>();
  private readonly actionState = signal<PendingCommand | null>(null);
  private readonly checkedAt = signal<Date | null>(null);
  private readonly notices = signal<readonly string[]>([]);

  readonly session = this.sessionState.session;
  readonly nodes = this.headers.asReadonly();
  readonly detail = this.currentDetail.asReadonly();
  readonly selection = this.currentSelection.asReadonly();
  readonly expanded = this.expansion.asReadonly();
  readonly query = this.filterQuery.asReadonly();
  readonly attention = this.attentionOnly.asReadonly();
  readonly fresh = this.connected.asReadonly();
  readonly treeLoading = this.loadingTree.asReadonly();
  readonly detailLoading = this.loadingDetail.asReadonly();
  readonly treeError = this.treeFailure.asReadonly();
  readonly detailError = this.detailFailure.asReadonly();
  readonly branchPages = this.branches.asReadonly();
  readonly searchTotal = this.matchTotal.asReadonly();
  readonly searchNext = this.matchNext.asReadonly();
  readonly projectLabel = this.projectName.asReadonly();
  readonly snapshotRevision = this.revision.asReadonly();
  readonly command = this.actionState.asReadonly();
  readonly lastChecked = this.checkedAt.asReadonly();
  readonly warnings = this.notices.asReadonly();
  readonly pending = computed(() => this.actionState()?.outcome === 'pending');
  readonly index = computed(() => new Map(this.headers().map((node) => [node.node_id, node])));
  readonly children = computed(() => {
    const map = new Map<string | null, WorkNode[]>();
    for (const node of this.headers()) {
      const children = map.get(node.parent_id) ?? [];
      children.push(node);
      map.set(node.parent_id, children);
    }
    return map;
  });
  readonly rows = computed(() => {
    const result: ExplorerRow[] = [],
      seen = new Set<string>();
    const visit = (parent: string | null, depth: number): void => {
      for (const node of this.children().get(parent) ?? []) {
        if (seen.has(node.node_id) || (this.matches() && !this.matches()?.has(node.node_id)))
          continue;
        seen.add(node.node_id);
        result.push({ node, depth });
        if (this.matches() || this.expansion().has(node.node_id)) visit(node.node_id, depth + 1);
      }
    };
    visit(null, 0);
    return result;
  });
  readonly breadcrumb = computed(() => {
    const path: WorkNode[] = [],
      seen = new Set<string>();
    let node = this.currentDetail()?.node;
    while (node && !seen.has(node.node_id)) {
      if (node.node_id !== 'project') {
        path.unshift(node);
      }
      seen.add(node.node_id);
      node = node.parent_id ? this.index().get(node.parent_id) : undefined;
    }
    return path;
  });

  constructor() {
    this.refreshRequests
      .pipe(
        switchMap(() => {
          this.connected.set(false);
          this.loadingTree.set(true);
          this.treeFailure.set(null);
          return this.api.tree(this.treeQuery()).pipe(
            switchMap((page) => {
              this.assertPage(page);
              const queries =
                this.filterQuery() || this.attentionOnly()
                  ? []
                  : [...this.expansion()].map((parent) =>
                      this.api.tree({ project: page.project_id, parent }).pipe(
                        catchError((error) => {
                          this.updateBranch(parent, {
                            next: null,
                            loading: false,
                            error: apiError(error),
                          });
                          return of(null);
                        }),
                      ),
                    );
              return queries.length
                ? forkJoin(queries).pipe(map((children) => ({ page, children })))
                : of({ page, children: [] as (NodePage | null)[] });
            }),
            tap(({ page, children }) => {
              for (const child of children)
                if (child && child.revision !== page.revision)
                  throw new ApiError(
                    'stale',
                    'The project changed during loading. Refresh the snapshot.',
                  );
              this.revision.set(page.revision);
              this.cursor = page.cursor;
              this.headers.set([
                ...new Map(
                  [...page.ancestors, ...page.nodes].map((node) => [node.node_id, node]),
                ).values(),
              ]);
              this.notices.set(page.warnings ?? []);
              this.setMatches(page, false);
              const project = page.nodes.find((node) => node.node_id === 'project');
              if (project) this.projectName.set(project.label);
              for (const child of children)
                if (child) {
                  this.merge([...child.ancestors, ...child.nodes]);
                  const parent = child.nodes[0]?.parent_id;
                  if (parent)
                    this.updateBranch(parent, {
                      next: child.next_offset,
                      loading: false,
                      error: null,
                    });
                }
              this.connected.set(true);
              this.checkedAt.set(new Date());
              this.selectionRequests.next(this.currentSelection());
            }),
            catchError((error) => {
              this.treeFailure.set(apiError(error));
              return EMPTY;
            }),
            finalize(() => this.loadingTree.set(false)),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();

    this.selectionRequests
      .pipe(
        switchMap((selection) => {
          if (!this.revision()) return EMPTY;
          this.loadingDetail.set(true);
          this.detailFailure.set(null);
          this.currentDetail.set(null);
          const revision = this.revision();
          return this.api.detail(this.projectId(), selection.nodeId, revision).pipe(
            switchMap((detail) => {
              if (detail.project_id !== this.projectId() || detail.revision !== revision)
                throw new ApiError('stale', 'The selected context no longer matches the snapshot.');
              if (
                (selection.artifact && selection.artifact !== detail.changeset_digest) ||
                (selection.run && selection.run !== detail.run_id)
              )
                throw new ApiError(
                  'stale',
                  'The pinned artifact or run is no longer current. Open this item again to inspect its current evidence.',
                );
              this.merge([detail.node]);
              return this.ancestors(detail.node, revision).pipe(map(() => detail));
            }),
            tap((detail) => {
              if (detail.revision !== this.revision())
                throw new ApiError('stale', 'The selected evidence changed while loading.');
              this.currentDetail.set(detail);
              if (detail.node.child_count && !this.matches()) this.loadBranch(detail.node.node_id);
            }),
            catchError((error) => {
              this.detailFailure.set(apiError(error));
              return EMPTY;
            }),
            finalize(() => this.loadingDetail.set(false)),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();

    this.searchRequests
      .pipe(
        debounceTime(180),
        distinctUntilChanged(),
        tap((query) => {
          this.filterQuery.set(query);
          this.refresh();
        }),
        takeUntilDestroyed(),
      )
      .subscribe();
  }

  start(): void {
    if (this.started) return;
    const capabilities = this.sessionState.session()?.access?.capabilities;
    if (capabilities && (!capabilities.includes('plan.read') || !capabilities.includes('run.read')))
      return;
    this.started = true;
    this.refresh();
    timer(2000, 2000)
      .pipe(
        filter(() => this.document.visibilityState !== 'hidden'),
        exhaustMap(() =>
          this.api.events(this.projectId(), this.cursor, this.revision()).pipe(
            tap((event) => {
              if (event.project_id !== this.projectId())
                throw new ApiError('forbidden', 'An update belongs to another project.');
              if (event.changed || !this.connected()) this.refresh();
              else this.checkedAt.set(new Date());
            }),
            catchError((error) => {
              this.connected.set(false);
              this.treeFailure.set(apiError(error));
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  refresh(): void {
    this.refreshRequests.next();
  }
  select(selection: Selection): void {
    this.currentSelection.set(selection);
    this.selectionRequests.next(selection);
  }
  search(query: string): void {
    this.searchRequests.next(query.slice(0, 128));
  }
  toggleAttention(): void {
    this.attentionOnly.update((value) => !value);
    this.refresh();
  }
  toggle(node: WorkNode): void {
    const next = new Set(this.expansion());
    if (next.has(node.node_id)) next.delete(node.node_id);
    else {
      next.add(node.node_id);
      this.loadBranch(node.node_id);
    }
    this.expansion.set(next);
  }
  loadBranch(parent: string, more = false): void {
    const state = this.branches().get(parent);
    if (state?.loading || (more && state?.next === null)) return;
    const revision = this.revision();
    this.updateBranch(parent, { next: state?.next ?? 0, loading: true, error: null });
    this.api
      .tree({ project: this.projectId(), parent, offset: String(more ? (state?.next ?? 0) : 0) })
      .pipe(
        tap((page) => {
          this.assertPage(page);
          if (revision !== this.revision() || page.revision !== revision)
            throw new ApiError('stale', 'This branch changed. Refresh before loading more.');
          this.merge([...page.ancestors, ...page.nodes]);
          this.updateBranch(parent, { next: page.next_offset, loading: false, error: null });
        }),
        catchError((error) => {
          this.updateBranch(parent, {
            next: state?.next ?? null,
            loading: false,
            error: apiError(error),
          });
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  moreMatches(): void {
    const offset = this.matchNext();
    if (offset === null) return;
    const revision = this.revision(),
      query = this.filterQuery(),
      attention = this.attentionOnly();
    this.api
      .tree({ ...this.treeQuery(), offset: String(offset) })
      .pipe(
        tap((page) => {
          if (
            revision !== this.revision() ||
            query !== this.filterQuery() ||
            attention !== this.attentionOnly()
          )
            return;
          this.assertPage(page);
          if (page.revision !== revision)
            throw new ApiError('stale', 'Search results changed. Refresh the search.');
          this.merge([...page.ancestors, ...page.nodes]);
          this.setMatches(page, true);
        }),
        catchError((error) => {
          this.treeFailure.set(apiError(error));
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
  label(id: string): string {
    return this.index().get(id)?.label ?? id;
  }
  node(id: string): WorkNode | undefined {
    return this.index().get(id);
  }
  requestAction(detail: WorkDetail, kind: ActionKind): void {
    if (
      !this.connected() ||
      this.pending() ||
      this.currentDetail() !== detail ||
      !detail.actions.some((action) => action.kind === kind && action.available)
    )
      return;
    this.send(
      {
        project_id: detail.project_id,
        node_id: detail.node.node_id,
        expected_revision: detail.revision,
        changeset_id: detail.changeset_id,
        kind,
        request_id: crypto.randomUUID(),
      },
      detail.node.label,
    );
  }
  retryCommand(): void {
    const command = this.actionState();
    if (command?.outcome === 'unknown') this.send(command.request, command.label);
  }
  dismissReceipt(): void {
    if (!this.pending()) this.actionState.set(null);
  }

  private projectId(): string {
    return this.sessionState.require().project_id;
  }
  private treeQuery(): TreeQuery {
    return {
      project: this.projectId(),
      query: this.filterQuery(),
      attention: this.attentionOnly() ? '1' : '0',
    };
  }
  private assertPage(page: NodePage): void {
    if (
      page.project_id !== this.projectId() ||
      (page.schema_version !== undefined && page.schema_version !== 1)
    )
      throw new ApiError(
        'forbidden',
        'The returned snapshot is outside the current project or protocol.',
      );
  }
  private merge(nodes: readonly WorkNode[]): void {
    this.headers.update((old) => [
      ...new Map([...old, ...nodes].map((node) => [node.node_id, node])).values(),
    ]);
  }
  private updateBranch(id: string, page: BranchPage): void {
    this.branches.update((old) => new Map([...old, [id, page]]));
  }
  private setMatches(page: NodePage, append: boolean): void {
    if (!this.filterQuery() && !this.attentionOnly()) {
      this.matches.set(null);
      this.matchNext.set(null);
      return;
    }
    this.matches.set(
      new Set([
        ...(append ? (this.matches() ?? []) : []),
        ...[...page.ancestors, ...page.nodes].map((node) => node.node_id),
      ]),
    );
    this.matchTotal.set(page.total);
    this.matchNext.set(page.next_offset);
  }
  private ancestors(node: WorkNode, revision: string, seen = new Set<string>()): Observable<void> {
    if (!node.parent_id) return of(undefined);
    if (seen.has(node.parent_id))
      throw new ApiError('server', 'The ownership hierarchy is invalid.');
    seen.add(node.parent_id);
    return this.api.detail(this.projectId(), node.parent_id, revision).pipe(
      tap((detail) => {
        if (detail.revision !== revision) throw new ApiError('stale', 'The ancestor path changed.');
        this.merge([detail.node]);
        this.expansion.update((old) => new Set([...old, detail.node.node_id]));
        if (!this.branches().has(detail.node.node_id)) this.loadBranch(detail.node.node_id);
      }),
      switchMap((detail) => this.ancestors(detail.node, revision, seen)),
    );
  }
  private send(request: WorkCommand, label: string): void {
    if (this.pending()) return;
    this.actionState.set({ request, label, outcome: 'pending', receipt: null });
    this.api
      .command(request)
      .pipe(
        tap((receipt) => {
          this.actionState.set({ request, label, outcome: 'received', receipt });
          this.refresh();
        }),
        catchError((error) => {
          const failure = apiError(error),
            unknown = failure.kind === 'offline' || failure.kind === 'server';
          this.actionState.set({
            request,
            label,
            outcome: unknown ? 'unknown' : 'rejected',
            receipt: null,
          });
          this.treeFailure.set(failure);
          if (unknown) this.connected.set(false);
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
}
