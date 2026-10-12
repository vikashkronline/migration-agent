import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { WorkbenchStore } from '../../workbench-store';

@Component({
  selector: 'cc-checks-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (store.detail(); as detail) {
      @if (detail.node.status === 'VALIDATION_FAILED' && !detail.evidence.length) {
        <div class="alert alert-danger py-2 px-3 mb-3">
          <strong>Validation Refusal / Gate Failure:</strong>
          <p class="small mb-0 mt-1">
            {{
              detail.recovery_note ||
                'Validation was refused by execution policy or execution gate. Check the activity tab for detailed logs.'
            }}
          </p>
        </div>
      }
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <caption>
            Validation evidence for the selected task and artifact
          </caption>
          <thead>
            <tr>
              <th scope="col">Evidence</th>
              <th scope="col">Recorded result</th>
            </tr>
          </thead>
          <tbody>
            @for (check of detail.evidence; track $index) {
              <tr>
                <th scope="row">{{ check[0] }}</th>
                <td>{{ check[1] }}</td>
              </tr>
            } @empty {
              <tr>
                <td colspan="2">No validation execution evidence recorded.</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <p class="small text-body-secondary">
        A recorded pass does not replace freshness checks at execution. Optional journeys remain
        separate from required validation.
      </p>
    }
  `,
})
export class ChecksPage {
  protected readonly store = inject(WorkbenchStore);
}
