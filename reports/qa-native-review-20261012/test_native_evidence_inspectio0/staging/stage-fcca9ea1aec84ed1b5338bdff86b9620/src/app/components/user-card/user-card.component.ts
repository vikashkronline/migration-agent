import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';

@Component({
  selector: 'app-user-card',
  standalone: true,
  templateUrl: './user-card.component.html',
  styleUrls: ['./user-card.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UserCardComponent {
  readonly description = input<string>('');
  readonly name = input<string>('');

  readonly isExpanded = signal<boolean>(false);

  toggleDetails(): void {
    this.isExpanded.update((current) => !current);
  }
}
