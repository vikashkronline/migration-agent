import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RunSummaryView } from '../../services/control-api.service';

@Component({
  selector: 'app-run-list',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="card mb-4">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span class="fw-bold">Recorded Migration Runs</span>
        <button class="btn btn-sm btn-outline-secondary" (click)="refresh.emit()">Refresh</button>
      </div>
      <div class="card-body p-0">
        <table class="table table-hover table-sm mb-0">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            @if (runs.length === 0) {
              <tr>
                <td colspan="4" class="text-center text-muted py-3">No runs recorded yet.</td>
              </tr>
            } @else {
              @for (run of runs; track run.run_id) {
                <tr
                  [class.table-active]="run.run_id === selectedRunId"
                  style="cursor: pointer;"
                  (click)="runSelected.emit(run.run_id)"
                >
                  <td class="fw-semibold text-info">{{ run.run_id }}</td>
                  <td>{{ run.plan_id }}</td>
                  <td>
                    @if (run.has_recovery_required || run.terminal_state === 'RECOVERY_REQUIRED') {
                      <span class="badge bg-warning text-dark">RECOVERY REQUIRED</span>
                    } @else if (run.status === 'COMPLETED') {
                      <span class="badge bg-success">COMPLETED</span>
                    } @else if (run.status === 'FAILED') {
                      <span class="badge bg-danger">FAILED</span>
                    } @else {
                      <span class="badge bg-secondary">{{ run.status }}</span>
                    }
                  </td>
                  <td class="text-muted small">{{ run.updated_at }}</td>
                </tr>
              }
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: [`
    :host {
      display: block;
    }
  `],
})
export class RunListComponent {
  @Input({ required: true }) runs: RunSummaryView[] = [];
  @Input() selectedRunId: string | null = null;
  @Output() runSelected = new EventEmitter<string>();
  @Output() refresh = new EventEmitter<void>();
}
