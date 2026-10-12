import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

@Component({
  selector: 'cc-code-line',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template:
    '@for (token of tokens(); track $index) {<span [class]="token.style">{{token.text}}</span>}@if (isNonStandard()) {<span class="badge text-bg-warning ms-1 font-monospace" title="Non-standard CRLF line ending">[CRLF]</span>} @else if (showEnding() && ending()) {<span class="small text-body-secondary font-monospace ms-1">[{{ending()}}]</span>}',
  styles: ':host { white-space: pre-wrap; overflow-wrap: anywhere; }',
})
export class CodeLine {
  readonly text = input.required<string>();
  readonly showEnding = input(false);
  protected readonly ending = computed(() =>
    this.text().endsWith('\r\n') ? 'CRLF' : this.text().endsWith('\n') ? 'LF' : '',
  );
  protected readonly isNonStandard = computed(() => this.ending() === 'CRLF');
  protected readonly tokens = computed(() => {
    const text = this.text(),
      result: { text: string; style: string }[] = [];
    const pattern =
      /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\/\/[^\r\n]*|\b(?:const|let|function|class|return|import|export|from|if|else|true|false|null|def|async|await)\b|\b\d+(?:\.\d+)?\b)/g;
    let offset = 0;
    for (const match of text.matchAll(pattern)) {
      const start = match.index,
        value = match[0];
      if (start > offset) result.push({ text: text.slice(offset, start), style: '' });
      result.push({
        text: value,
        style: value.startsWith('//')
          ? 'text-body-secondary'
          : /^["']/.test(value)
            ? 'text-success-emphasis'
            : 'text-primary-emphasis',
      });
      offset = start + value.length;
    }
    if (offset < text.length) result.push({ text: text.slice(offset), style: '' });
    return result;
  });
}
