import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiffReviewView } from '../../services/control-api.service';

@Component({
  selector: 'app-diff-viewer',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!diffData || diffData.files.length === 0) {
      <div class="text-center text-muted py-5">
        <div class="mb-2">📄</div>
        <div>No staged file modifications for this run.</div>
      </div>
    } @else {
      <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
          <span class="fw-bold">{{ diffData.total_files }} file(s) modified</span>
          <span class="badge bg-success ms-2">+{{ diffData.total_additions }}</span>
          <span class="badge bg-danger ms-1">-{{ diffData.total_deletions }}</span>
        </div>
        <div class="small text-muted">
          Digest: <code class="text-info">{{ diffData.changeset_digest?.slice(0, 16) }}...</code>
        </div>
      </div>

      @for (file of diffData.files; track file.path) {
        <div class="card mb-3">
          <div class="card-header d-flex justify-content-between align-items-center py-2">
            <div class="d-flex align-items-center gap-2">
              <span
                class="badge"
                [class.bg-success]="file.change_type === 'CREATE'"
                [class.bg-danger]="file.change_type === 'DELETE'"
                [class.bg-primary]="file.change_type === 'MODIFY'"
              >
                {{ file.change_type }}
              </span>
              <span class="fw-semibold small">{{ file.path }}</span>
            </div>
            <div>
              <span class="badge bg-success small">+{{ file.additions }}</span>
              <span class="badge bg-danger small ms-1">-{{ file.deletions }}</span>
            </div>
          </div>
          <div class="card-body p-0">
            <pre class="diff-container p-2 m-0"><code>{{ file.patch }}</code></pre>
          </div>
        </div>
      }
    }
  `,
  styles: [`
    .diff-container {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      background-color: #0b0e14;
      white-space: pre-wrap;
      word-break: break-all;
    }
  `],
})
export class DiffViewerComponent {
  @Input() diffData: DiffReviewView | null = null;
}
