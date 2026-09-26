import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ControlApiService,
  DiffReviewView,
  GraphView,
  PlanView,
  RunDetailView,
  RunSummaryView,
} from './services/control-api.service';
import { EventSocketService } from './services/event-socket.service';
import { RunListComponent } from './components/run-list/run-list.component';
import { DiffViewerComponent } from './components/diff-viewer/diff-viewer.component';
import { PlanDetailComponent } from './components/plan-detail/plan-detail.component';
import { GraphViewerComponent } from './components/graph-viewer/graph-viewer.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RunListComponent,
    DiffViewerComponent,
    PlanDetailComponent,
    GraphViewerComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="navbar navbar-expand navbar-dark px-3 py-2 sticky-top border-bottom border-secondary bg-dark">
      <div class="d-flex align-items-center gap-2">
        <span class="fs-5 fw-bold text-info">⚡ Migration Agent</span>
        <span class="text-muted small">| Control Center (Loopback 127.0.0.1)</span>
      </div>
      <div class="ms-auto d-flex align-items-center gap-3">
        @if (socketService.isConnected()) {
          <span class="badge bg-success">Live Connected</span>
        } @else {
          <span class="badge bg-secondary">Connecting...</span>
        }
        <span class="badge bg-dark border text-muted small">Mode B Session</span>
      </div>
    </header>

    <div class="container-fluid">
      <div class="row">
        <nav class="col-md-2 d-md-block bg-dark border-end border-secondary py-3 px-2 min-vh-100">
          <div class="nav flex-column gap-1">
            <button
              class="nav-link text-start"
              [class.active]="activeTab() === 'runs'"
              (click)="switchTab('runs')"
            >
              📊 Runs & Progress
            </button>
            <button
              class="nav-link text-start"
              [class.active]="activeTab() === 'diff'"
              (click)="switchTab('diff')"
            >
              🔍 Side-by-Side Diff
            </button>
            <button
              class="nav-link text-start"
              [class.active]="activeTab() === 'plan'"
              (click)="switchTab('plan')"
            >
              ✍️ Plan & Approvals
            </button>
            <button
              class="nav-link text-start"
              [class.active]="activeTab() === 'graph'"
              (click)="switchTab('graph')"
            >
              🕸️ Cross-Domain Graph
            </button>
            <button
              class="nav-link text-start"
              [class.active]="activeTab() === 'doctor'"
              (click)="switchTab('doctor')"
            >
              🩺 Health & Doctor
            </button>
          </div>
        </nav>

        <main class="col-md-10 ms-sm-auto px-md-4 py-4">
          @switch (activeTab()) {
            @case ('runs') {
              <div class="row">
                <div class="col-md-7">
                  <app-run-list
                    [runs]="runs()"
                    [selectedRunId]="selectedRunId()"
                    (runSelected)="onRunSelected($event)"
                    (refresh)="loadRuns()"
                  ></app-run-list>
                </div>
                <div class="col-md-5">
                  <div class="card">
                    <div class="card-header fw-bold">Run Details & Checkpoints</div>
                    <div class="card-body">
                      @if (selectedRun(); as r) {
                        <div class="mb-3">
                          <span class="text-muted small">Run ID:</span>
                          <span class="fw-bold ms-1 text-info">{{ r.run_id }}</span>
                        </div>
                        <div class="mb-3">
                          <div class="fw-semibold small mb-2">Checkpoints ({{ r.checkpoints.length }}):</div>
                          <div class="list-group small">
                            @for (cp of r.checkpoints; track cp.checkpoint_id) {
                              <div class="list-group-item bg-transparent text-light border-secondary py-2">
                                <div class="d-flex justify-content-between">
                                  <span class="fw-bold text-info">{{ cp.type }}</span>
                                  <span class="text-muted small">{{ cp.timestamp }}</span>
                                </div>
                              </div>
                            }
                          </div>
                        </div>
                      } @else {
                        <p class="text-muted">Select a run from the list to inspect checkpoints.</p>
                      }
                    </div>
                  </div>
                </div>
              </div>
            }
            @case ('diff') {
              <app-diff-viewer [diffData]="diffData()"></app-diff-viewer>
            }
            @case ('plan') {
              <app-plan-detail
                [plan]="planData()"
                (approve)="onApprovePlan($event)"
                (apply)="onApplyRun()"
              ></app-plan-detail>
            }
            @case ('graph') {
              <app-graph-viewer [graph]="graphData()"></app-graph-viewer>
            }
            @case ('doctor') {
              <div class="card">
                <div class="card-header fw-bold">Health & Diagnostics</div>
                <div class="card-body">
                  <pre class="bg-dark text-light p-3 rounded">{{ healthData() | json }}</pre>
                </div>
              </div>
            }
          }
        </main>
      </div>
    </div>
  `,
  styles: [`
    .nav-link {
      color: #8b949e;
      border-radius: 6px;
      padding: 8px 12px;
      cursor: pointer;
      background: none;
      border: none;
    }
    .nav-link:hover, .nav-link.active {
      background-color: rgba(56, 139, 253, 0.15);
      color: #58a6ff;
      font-weight: 500;
    }
  `],
})
export class AppComponent implements OnInit {
  private readonly api = inject(ControlApiService);
  readonly socketService = inject(EventSocketService);

  readonly activeTab = signal<string>('runs');
  readonly runs = signal<RunSummaryView[]>([]);
  readonly selectedRunId = signal<string | null>(null);
  readonly selectedRun = signal<RunDetailView | null>(null);
  readonly diffData = signal<DiffReviewView | null>(null);
  readonly planData = signal<PlanView | null>(null);
  readonly graphData = signal<GraphView | null>(null);
  readonly healthData = signal<any>(null);

  ngOnInit(): void {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token') || '';
    if (token) {
      this.api.setSessionToken(token);
      this.socketService.connect(token);
    }
    this.loadRuns();
    this.loadHealth();
  }

  switchTab(tab: string): void {
    this.activeTab.set(tab);
    if (tab === 'runs') this.loadRuns();
    if (tab === 'graph') this.loadGraph();
    if (tab === 'doctor') this.loadHealth();
  }

  loadRuns(): void {
    this.api.listRuns().subscribe({
      next: (runs) => {
        this.runs.set(runs);
        if (runs.length > 0 && !this.selectedRunId()) {
          this.onRunSelected(runs[0].run_id);
        }
      },
    });
  }

  loadHealth(): void {
    this.api.getHealth().subscribe({
      next: (data) => this.healthData.set(data),
    });
  }

  loadGraph(): void {
    this.api.getGraph().subscribe({
      next: (data) => this.graphData.set(data),
    });
  }

  onRunSelected(runId: string): void {
    this.selectedRunId.set(runId);
    this.api.getRun(runId).subscribe({
      next: (detail) => {
        this.selectedRun.set(detail);
        if (detail.plan_id) {
          this.api.getPlan(detail.plan_id).subscribe({
            next: (plan) => this.planData.set(plan),
          });
        }
      },
    });
    this.api.getDiff(runId).subscribe({
      next: (diff) => this.diffData.set(diff),
    });
  }

  onApprovePlan(event: { actor: string; notes: string }): void {
    const plan = this.planData();
    if (!plan) return;
    this.api.approvePlan(plan.plan_id, event.actor, event.notes).subscribe({
      next: (updatedPlan) => {
        this.planData.set(updatedPlan);
        this.loadRuns();
      },
    });
  }

  onApplyRun(): void {
    const runId = this.selectedRunId();
    if (!runId) return;
    this.api.applyRun(runId, 'local-developer').subscribe({
      next: (detail) => {
        this.selectedRun.set(detail);
        this.loadRuns();
      },
    });
  }
}
