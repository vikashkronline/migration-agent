import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Input,
  OnChanges,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { GraphView } from '../../services/control-api.service';

declare const mermaid: any;

@Component({
  selector: 'app-graph-viewer',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span class="fw-bold">Cross-Domain Architecture Flowchart</span>
        <span class="badge bg-dark border text-muted small">Mermaid Strict Security</span>
      </div>
      <div class="card-body p-2">
        <div #diagramContainer class="mermaid-diagram-box">
          @if (!graph || !graph.mermaid_source) {
            <div class="text-muted">No graph source available.</div>
          }
        </div>
      </div>
    </div>
  `,
  styles: [`
    .mermaid-diagram-box {
      background-color: #0d1117;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 16px;
      min-height: 350px;
      display: flex;
      justify-content: center;
      align-items: center;
      overflow-x: auto;
    }
  `],
})
export class GraphViewerComponent implements AfterViewInit, OnChanges {
  @Input() graph: GraphView | null = null;
  @ViewChild('diagramContainer') container!: ElementRef<HTMLDivElement>;

  ngAfterViewInit(): void {
    this.renderDiagram();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['graph'] && this.container) {
      this.renderDiagram();
    }
  }

  private renderDiagram(): void {
    if (!this.container || !this.graph || !this.graph.mermaid_source) return;

    if (typeof mermaid !== 'undefined') {
      try {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'dark',
        });
        const id = `mermaid-svg-${Date.now()}`;
        mermaid.render(id, this.graph.mermaid_source).then((res: { svg: string }) => {
          this.container.nativeElement.innerHTML = res.svg;
        });
      } catch (err) {
        this.container.nativeElement.innerHTML = `<pre class="text-light p-3 small">${this.graph.mermaid_source}</pre>`;
      }
    } else {
      this.container.nativeElement.innerHTML = `<pre class="text-light p-3 small">${this.graph.mermaid_source}</pre>`;
    }
  }
}
