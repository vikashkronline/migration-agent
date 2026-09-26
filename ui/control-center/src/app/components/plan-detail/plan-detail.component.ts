import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { PlanView } from '../../services/control-api.service';

@Component({
  selector: 'app-plan-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!plan) {
      <div class="text-muted text-center py-5">No active plan found for this run.</div>
    } @else {
      <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h4 class="mb-1 fw-bold">Plan: {{ plan.plan_id }}</h4>
          <div class="text-muted small">
            Content Digest: <code class="text-info">{{ plan.plan_digest.slice(0, 24) }}...</code>
          </div>
        </div>
        <div class="d-flex align-items-center gap-3">
          @if (plan.is_approved) {
            <span class="badge bg-success">APPROVED</span>
            <button class="btn btn-primary fw-bold px-3" (click)="apply.emit()">Apply to Target</button>
          } @else {
            <span class="badge bg-warning text-dark">NEEDS APPROVAL</span>
            <button class="btn btn-success fw-bold px-3" (click)="submitApproval()">Sign & Approve</button>
          }
        </div>
      </div>

      <div class="row mb-4">
        <div class="col-md-8">
          <h5 class="fw-bold mb-3">Migration Steps ({{ plan.steps.length }})</h5>
          <div class="d-flex flex-column gap-3">
            @for (step of plan.steps; track step.step_id; let idx = $index) {
              <div class="card">
                <div class="card-body">
                  <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="fw-bold text-accent">{{ idx + 1 }}. {{ step.title }}</div>
                    <span
                      class="badge"
                      [class.bg-danger]="step.risk === 'HIGH'"
                      [class.bg-warning]="step.risk === 'MEDIUM'"
                      [class.text-dark]="step.risk === 'MEDIUM'"
                      [class.bg-secondary]="step.risk === 'LOW'"
                    >
                      {{ step.risk }} RISK
                    </span>
                  </div>
                  <p class="small text-muted mb-2">{{ step.description }}</p>
                  <div class="d-flex flex-wrap gap-1">
                    @for (file of step.expected_files; track file) {
                      <span class="badge bg-dark border text-light small">{{ file }}</span>
                    }
                  </div>
                </div>
              </div>
            }
          </div>
        </div>

        <div class="col-md-4">
          <div class="card">
            <div class="card-header fw-bold small">Approval Authority (ADR-2)</div>
            <div class="card-body" [formGroup]="approvalForm">
              <div class="mb-3">
                <label class="form-label small text-muted">Actor Identity:</label>
                <input
                  type="text"
                  formControlName="actor"
                  class="form-control form-control-sm bg-dark text-light border-secondary"
                />
              </div>
              <div class="mb-3">
                <label class="form-label small text-muted">Approval Notes:</label>
                <textarea
                  formControlName="notes"
                  class="form-control form-control-sm bg-dark text-light border-secondary"
                  rows="2"
                  placeholder="Audit sign-off note..."
                ></textarea>
              </div>

              @if (plan.approval_signature) {
                <div class="p-2 rounded bg-dark border small">
                  <div class="fw-semibold text-success mb-1">✓ Signature Valid</div>
                  <div class="text-muted">Actor: {{ plan.approval_signature.actor }}</div>
                  <div class="text-muted">Signed: {{ plan.approval_signature.timestamp }}</div>
                </div>
              } @else {
                <div class="text-muted small">
                  This plan requires human verification before applying changes to target workspace.
                </div>
              }
            </div>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    :host {
      display: block;
    }
  `],
})
export class PlanDetailComponent {
  @Input() plan: PlanView | null = null;
  @Output() approve = new EventEmitter<{ actor: string; notes: string }>();
  @Output() apply = new EventEmitter<void>();

  readonly approvalForm = new FormGroup({
    actor: new FormControl<string>('local-developer', { nonNullable: true }),
    notes: new FormControl<string>('Approved via Control Center GUI', { nonNullable: true }),
  });

  submitApproval(): void {
    const val = this.approvalForm.getRawValue();
    this.approve.emit(val);
  }
}
