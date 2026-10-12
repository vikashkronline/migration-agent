import type { Routes } from '@angular/router';
import { projectGuard, startGuard } from './core/routing/project-guard';
import { WorkbenchStore } from './workbench/workbench-store';

export const APP_ROUTES: Routes = [
  {
    path: '',
    pathMatch: 'full',
    canActivate: [startGuard],
    loadComponent: () =>
      import('./core/routing/unavailable-page').then((module) => module.UnavailablePage),
  },
  {
    path: 'projects/:projectId',
    canActivate: [projectGuard],
    providers: [WorkbenchStore],
    loadComponent: () =>
      import('./workbench/shell/project-shell').then((module) => module.ProjectShell),
    loadChildren: () =>
      import('./workbench/workbench.routes').then((module) => module.WORKBENCH_ROUTES),
  },
  {
    path: 'unavailable',
    loadComponent: () =>
      import('./core/routing/unavailable-page').then((module) => module.UnavailablePage),
  },
  {
    path: '**',
    loadComponent: () =>
      import('./core/routing/unavailable-page').then((module) => module.UnavailablePage),
  },
];
