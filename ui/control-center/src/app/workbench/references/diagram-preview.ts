import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  linkedSignal,
  signal,
} from '@angular/core';
import { Feedback } from '../../shared/feedback/feedback';

@Component({
  selector: 'cc-diagram-preview',
  imports: [Feedback],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '@if (source()) {<button class="btn btn-outline-primary" [disabled]="loading()" (click)="render()">Render architecture diagram</button>@if (error()) {<cc-feedback title="Diagram unavailable" [message]="error()" />}@if (image()) {<img class="img-fluid d-block mt-3" [src]="image()" alt="Architecture diagram for the selected reference">}}',
})
export class DiagramPreview {
  readonly source = input.required<string>();
  readonly context = input.required<string>();
  private readonly content = linkedSignal<{ key: string; url: string } | null>(() => {
    this.context();
    this.source();
    return null;
  });
  protected readonly image = computed(() =>
    this.content()?.key === this.context() ? (this.content()?.url ?? '') : '',
  );
  protected readonly error = linkedSignal(() => {
    this.context();
    return '';
  });
  protected readonly loading = signal(false);
  protected async render(): Promise<void> {
    const key = this.context(),
      source = this.source();
    this.loading.set(true);
    this.error.set('');
    try {
      if (source.length > 16384 || source.includes('%%{') || /^\s*click\s/im.test(source))
        throw new Error('Unsupported diagram directives');
      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        flowchart: { htmlLabels: false },
      });
      const result = await mermaid.render('diagram-' + crypto.randomUUID(), source);
      if (key === this.context())
        this.content.set({
          key,
          url:
            'data:image/svg+xml;base64,' +
            btoa(
              Array.from(new TextEncoder().encode(result.svg), (byte) =>
                String.fromCharCode(byte),
              ).join(''),
            ),
        });
    } catch {
      if (key === this.context())
        this.error.set('Diagram could not be rendered safely. Inspect the source text.');
    } finally {
      this.loading.set(false);
    }
  }
}
