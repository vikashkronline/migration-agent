import { DOCUMENT } from '@angular/common';
import type { ElementRef } from '@angular/core';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  output,
  viewChild,
} from '@angular/core';

@Component({
  selector: 'cc-modal-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './modal-dialog.html',
})
export class ModalDialog {
  readonly open = input(false);
  readonly label = input.required<string>();
  readonly drawer = input(false);
  readonly dismissed = output<void>();
  private readonly document = inject(DOCUMENT);
  private readonly dialog = viewChild<ElementRef<HTMLDialogElement>>('dialog');
  private previousFocus: HTMLElement | null = null;
  private previousOverflow = '';

  constructor() {
    effect(() => {
      const dialog = this.dialog()?.nativeElement;
      if (!dialog) return;
      if (this.open() && !dialog.open) {
        this.previousFocus =
          this.document.activeElement instanceof HTMLElement ? this.document.activeElement : null;
        this.previousOverflow = this.document.body.style.overflow;
        this.document.body.style.overflow = 'hidden';
        dialog.showModal();
      } else if (!this.open() && dialog.open) this.closeNative(dialog);
    });
    inject(DestroyRef).onDestroy(() => {
      const dialog = this.dialog()?.nativeElement;
      if (dialog?.open) this.closeNative(dialog);
    });
  }

  protected dismiss(event?: Event): void {
    event?.preventDefault();
    this.dismissed.emit();
  }
  protected dismissBackdrop(event: MouseEvent): void {
    const dialog = this.dialog()?.nativeElement;
    if (!dialog || event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (
      event.clientX < box.left ||
      event.clientX > box.right ||
      event.clientY < box.top ||
      event.clientY > box.bottom
    )
      this.dismiss();
  }
  private closeNative(dialog: HTMLDialogElement): void {
    dialog.close();
    this.document.body.style.overflow = this.previousOverflow;
    if (this.previousFocus?.isConnected) this.previousFocus.focus();
  }
}
