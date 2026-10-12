import type { ErrorHandler } from '@angular/core';
import { Injectable, inject, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ApplicationErrors {
  private readonly value = signal(false);
  readonly failed = this.value.asReadonly();
  report(): void {
    this.value.set(true);
  }
}

@Injectable()
export class ApplicationErrorHandler implements ErrorHandler {
  private readonly errors = inject(ApplicationErrors);
  handleError(): void {
    this.errors.report();
  }
}
