import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import type { StatusTone } from '../../workbench/workbench.models';
import { CcIcon, type IconName } from '../icon/cc-icon';

@Component({
  selector: 'cc-status-badge',
  standalone: true,
  imports: [CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span
      class="badge d-inline-flex align-items-center gap-1 text-wrap"
      [class]="color()"
      [attr.title]="titleText()"
    >
      <cc-icon [name]="iconName()" size="0.85em" />
      <span>{{ label() }}</span>
    </span>
  `,
})
export class StatusBadge {
  readonly status = input.required<string>();
  readonly tone = input<StatusTone>('neutral');
  readonly kind = input<string | undefined>(undefined);
  readonly taskCount = input<number | undefined>(undefined);

  protected readonly label = computed(() => {
    const s = this.status();
    const k = this.kind();
    const count = this.taskCount();
    if (s === 'UNKNOWN') {
      if (k === 'group' && count === 0) {
        return 'unconfigured';
      }
      return 'unknown';
    }
    return s.replaceAll('_', ' ').toLowerCase();
  });

  protected readonly iconName = computed<IconName>(() => {
    const s = this.status();
    const t = this.tone();
    if (s === 'APPLY_COMPLETED') return 'check-circle-fill';
    if (s === 'STAGE_VERIFIED' || s === 'VALIDATION_PASSED') return 'patch-check-fill';
    if (s === 'APPROVAL_RECORDED' || s === 'READY_TO_APPLY') return 'lock';
    if (s === 'OBSERVED') return 'eye';
    if (s === 'PLANNED' || s === 'WORK_PENDING') return 'hourglass-split';
    if (
      t === 'danger' ||
      s === 'VALIDATION_FAILED' ||
      s === 'RECOVERY_REQUIRED' ||
      s === 'ATTENTION_REQUIRED'
    ) {
      return 'exclamation-triangle-fill';
    }
    if (t === 'warning') return 'hourglass-split';
    if (t === 'info') return 'eye';
    if (t === 'success') return 'check-circle-fill';
    return 'dash-circle';
  });

  protected readonly titleText = computed(() => {
    const s = this.status();
    if (s === 'UNKNOWN') {
      if (this.kind() === 'group' && this.taskCount() === 0) {
        return 'Unconfigured: No custom tasks or readiness criteria declared in this group.';
      }
      return 'Status unknown: no migration plan or workflow execution evidence recorded yet.';
    }
    if (s === 'MISSING_WORKFLOW_EVIDENCE') {
      return 'Declared in project-work but no matching workflow record found in the store.';
    }
    return s.replaceAll('_', ' ');
  });

  protected readonly color = computed(
    () =>
      'text-bg-' +
      (
        {
          neutral: 'secondary',
          info: 'info',
          success: 'success',
          warning: 'warning',
          danger: 'danger',
        } as const
      )[this.tone()],
  );
}
