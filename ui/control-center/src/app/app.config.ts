import type { ApplicationConfig } from '@angular/core';
import {
  ErrorHandler,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  provideRouter,
  withComponentInputBinding,
  withInMemoryScrolling,
  withNavigationErrorHandler,
  withRouterConfig,
} from '@angular/router';
import { APP_ROUTES } from './app.routes';
import { ApplicationErrorHandler, ApplicationErrors } from './core/errors/application-errors';
import { SessionAuth, sessionInterceptor } from './core/session/session-auth';
import { ThemePreferences } from './core/preferences/theme-preferences';

export const APP_CONFIG: ApplicationConfig = {
  providers: [
    provideZonelessChangeDetection(),
    provideBrowserGlobalErrorListeners(),
    provideAppInitializer(() => inject(SessionAuth).initialize()),
    provideAppInitializer(() => inject(ThemePreferences).initialize()),
    provideHttpClient(withInterceptors([sessionInterceptor])),
    provideRouter(
      APP_ROUTES,
      withComponentInputBinding(),
      withRouterConfig({ paramsInheritanceStrategy: 'always' }),
      withInMemoryScrolling({ scrollPositionRestoration: 'enabled' }),
      withNavigationErrorHandler(() => inject(ApplicationErrors).report()),
    ),
    { provide: ErrorHandler, useClass: ApplicationErrorHandler },
  ],
};
