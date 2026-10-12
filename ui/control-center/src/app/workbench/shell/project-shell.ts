import { DatePipe, DOCUMENT } from '@angular/common';
import type { OnInit } from '@angular/core';
import {
  ChangeDetectionStrategy,
  afterRenderEffect,
  Component,
  computed,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { RouterLink, RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { fromEvent, filter, map } from 'rxjs';
import { CcIcon } from '../../shared/icon/cc-icon';
import { Feedback } from '../../shared/feedback/feedback';
import { ModalDialog } from '../../shared/modal-dialog/modal-dialog';
import { ProjectExplorer } from '../explorer/project-explorer';
import { WorkbenchStore } from '../workbench-store';
import { ThemePreferences } from '../../core/preferences/theme-preferences';

@Component({
  selector: 'cc-project-shell',
  imports: [RouterOutlet, RouterLink, DatePipe, ProjectExplorer, ModalDialog, Feedback, CcIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './project-shell.html',
})
export class ProjectShell implements OnInit {
  protected readonly store = inject(WorkbenchStore);
  protected readonly workflowReadable = computed(() => {
    const capabilities = this.store.session()?.access?.capabilities;
    return Boolean(capabilities?.includes('plan.read') && capabilities.includes('run.read'));
  });
  protected readonly drawerOpen = signal(false);
  protected readonly theme = inject(ThemePreferences);
  private readonly document = inject(DOCUMENT);
  private readonly destroyRef = inject(DestroyRef);
  private readonly window = this.document.defaultView;
  private readonly router = inject(Router);
  private lastFocusUrl = '';

  constructor() {
    const url = toSignal(
      this.router.events.pipe(
        filter((event) => event instanceof NavigationEnd),
        map((event) => event.urlAfterRedirects),
      ),
      { initialValue: this.router.url },
    );
    afterRenderEffect(() => {
      const currentUrl = url(),
        detail = this.store.detail(),
        selection = this.store.selection();
      if (this.drawerOpen() || currentUrl === this.lastFocusUrl) return;
      if (currentUrl.includes('/items/') && (!detail || detail.node.node_id !== selection.nodeId))
        return;
      const heading = this.document.getElementById('content-heading');
      if (heading) {
        heading.focus();
        this.lastFocusUrl = currentUrl;
      }
    });
  }

  ngOnInit(): void {
    this.store.start();
    if (this.window)
      fromEvent(this.window, 'resize')
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => {
          if (this.drawerOpen() && this.window?.matchMedia('(min-width:768px)').matches) {
            this.lastFocusUrl = '';
            this.drawerOpen.set(false);
          }
        });
  }
  protected toggleTheme(): void {
    this.theme.toggle();
  }
  protected select(): void {
    this.lastFocusUrl = '';
    this.drawerOpen.set(false);
  }
  protected attention(): void {
    this.store.toggleAttention();
    if (this.window?.matchMedia('(max-width:767px)').matches) this.drawerOpen.set(true);
  }
}
