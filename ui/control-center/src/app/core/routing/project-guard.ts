import { inject } from '@angular/core';
import type { CanActivateFn } from '@angular/router';
import { Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { apiError } from '../api/api-error';
import { SessionState } from '../session/session-state';

export const projectGuard: CanActivateFn = (route) => {
  const session = inject(SessionState),
    router = inject(Router);
  return session.ensure().pipe(
    map((value) =>
      route.paramMap.get('projectId') === value.project_id
        ? true
        : router.createUrlTree(['/unavailable'], { queryParams: { reason: 'project' } }),
    ),
    catchError((error) =>
      of(router.createUrlTree(['/unavailable'], { queryParams: { reason: apiError(error).kind } })),
    ),
  );
};
export const startGuard: CanActivateFn = () => {
  const session = inject(SessionState),
    router = inject(Router);
  return session.ensure().pipe(
    map((value) =>
      router.createUrlTree(
        value.access &&
          (!value.access.capabilities.includes('plan.read') ||
            !value.access.capabilities.includes('run.read')) &&
          value.access.capabilities.includes('configuration.read')
          ? ['/projects', value.project_id, 'settings', 'overview']
          : ['/projects', value.project_id, 'items', 'project'],
      ),
    ),
    catchError((error) =>
      of(router.createUrlTree(['/unavailable'], { queryParams: { reason: apiError(error).kind } })),
    ),
  );
};
