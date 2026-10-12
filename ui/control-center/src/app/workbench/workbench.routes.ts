import type { Routes } from '@angular/router';
import { inject } from '@angular/core';
import { Router } from '@angular/router';

const legacySections: Readonly<Record<string, string>> = {
  Summary: 'summary',
  Steps: 'steps',
  Checks: 'checks',
  Artifacts: 'artifacts',
  Activity: 'activity',
  Decision: 'decision',
  Ask: 'ask',
};
export const WORKBENCH_ROUTES: Routes = [
  { path: 'settings', redirectTo: 'settings/overview', pathMatch: 'full' },
  {
    path: 'settings/:section',
    title: 'Project settings · Control Center',
    canDeactivate: [
      (component: { canLeave(): boolean | Promise<boolean> }) => component.canLeave(),
    ],
    loadComponent: () => import('./settings/settings-page').then((module) => module.SettingsPage),
  },
  {
    path: 'access',
    title: 'Users and access · Control Center',
    loadComponent: () => import('./access/access-page').then((module) => module.AccessPage),
  },
  {
    path: 'wizard/foundation',
    title: 'Stack & Foundation Wizard · Control Center',
    loadComponent: () => import('./wizard/stack-wizard').then((module) => module.StackWizardPage),
  },
  {
    path: 'stack',
    redirectTo: 'wizard/foundation',
    pathMatch: 'full',
  },
  { path: '', pathMatch: 'full', redirectTo: 'items/project' },
  {
    path: 'health',
    title: 'Platform health · Control Center',
    loadComponent: () => import('./health/health-page').then((module) => module.HealthPage),
  },
  {
    path: 'runs',
    title: 'Runs · Control Center',
    loadComponent: () => import('./runs/runs-page').then((module) => module.RunsPage),
  },
  {
    path: 'items/:nodeId',
    loadComponent: () => import('./item/item-page').then((module) => module.ItemPage),
    children: [
      {
        path: '',
        pathMatch: 'full',
        redirectTo: (data) => {
          const view: unknown = data.queryParams['view'];
          const section =
            typeof view === 'string' ? (legacySections[view] ?? 'unsupported') : 'summary';
          const queryParams = { ...data.queryParams };
          delete queryParams['view'];
          return inject(Router).createUrlTree(
            ['/projects', data.params['projectId'], 'items', data.params['nodeId'], section],
            { queryParams },
          );
        },
      },
      {
        path: 'summary',
        title: 'Summary · Control Center',
        loadComponent: () =>
          import('./item/summary/summary-page').then((module) => module.SummaryPage),
      },
      {
        path: 'steps',
        title: 'Steps · Control Center',
        loadComponent: () => import('./item/steps/steps-page').then((module) => module.StepsPage),
      },
      {
        path: 'checks',
        title: 'Checks · Control Center',
        loadComponent: () =>
          import('./item/checks/checks-page').then((module) => module.ChecksPage),
      },
      {
        path: 'artifacts',
        title: 'Artifacts · Control Center',
        loadComponent: () =>
          import('./item/artifacts/artifacts-page').then((module) => module.ArtifactsPage),
      },
      {
        path: 'activity',
        title: 'Activity · Control Center',
        loadComponent: () =>
          import('./item/activity/activity-page').then((module) => module.ActivityPage),
      },
      {
        path: 'decision',
        title: 'Decision · Control Center',
        loadComponent: () =>
          import('./item/decision/decision-page').then((module) => module.DecisionPage),
      },
      {
        path: 'ask',
        title: 'Ask · Control Center',
        loadComponent: () => import('./item/ask/ask-page').then((module) => module.AskPage),
      },
      {
        path: '**',
        loadComponent: () =>
          import('../core/routing/unavailable-page').then((module) => module.UnavailablePage),
      },
    ],
  },
  {
    path: '**',
    loadComponent: () =>
      import('../core/routing/unavailable-page').then((module) => module.UnavailablePage),
  },
];
