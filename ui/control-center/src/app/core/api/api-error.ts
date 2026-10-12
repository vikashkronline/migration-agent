import { HttpErrorResponse } from '@angular/common/http';

export type ErrorKind =
  | 'session'
  | 'forbidden'
  | 'missing'
  | 'stale'
  | 'rejected'
  | 'offline'
  | 'server';
export class ApiError extends Error {
  constructor(
    readonly kind: ErrorKind,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function apiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof Error && error.name === 'TimeoutError')
    return new ApiError(
      'offline',
      'The response timed out. Recover the same request before sending another change.',
    );
  if (!(error instanceof HttpErrorResponse))
    return new ApiError(
      'server',
      'The request could not be completed. Refresh the current context.',
    );
  const payload = error.error as { error?: { message?: unknown } } | null;
  const message = payload?.error?.message;
  const reason = typeof message === 'string' ? (message.split(':', 1)[0] ?? '') : '';
  const accessReasons: Readonly<Record<string, string>> = {
    CONFIGURATION_STALE:
      'Configuration changed. Refresh and reconcile your edits before making a new request.',
    CONFIGURATION_UNSAFE_ROOTS:
      'Use separate source, governance, state, staging, trust and preference roots.',
    CONFIGURATION_INVALID:
      'A configuration check failed. Inspect the field checks and active project constraints.',
    CONFIGURATION_MODEL_INVALID:
      'Use unique model identifiers and select a default included in that profile.',
    CONFIGURATION_PROFILE_INVALID:
      'Profile identifiers must be unique and the default must name a profile.',
    CONFIGURATION_SECRET_REJECTED:
      'Credentials and secret-shaped values cannot be saved. Configure authentication outside the GUI.',
    CONFIGURATION_SCHEMA_UNSUPPORTED:
      'The existing configuration schema is unsupported. Preserve its bytes and review a deliberate upgrade.',
    CONFIGURATION_OWNER_SETUP_REQUIRED: 'Ask an owner to activate an approved runtime profile.',
    CONFIGURATION_CONTEXT_CHANGED:
      'The operation lost its authority context. Refresh permissions before proceeding.',
    CONFIGURATION_REQUEST_CONFLICT:
      'This request ID already names different input. Recover the original request before starting a new one.',
    LAST_OWNER:
      'Keep at least one active, non-expiring owner with an enrolled key and administration permissions.',
    ACCESS_CHANGED: 'Access changed. Refresh permissions and prepare the proposal again.',
    ACCESS_EXPIRED: 'This proposal expired. Prepare a new proposal and review its exact digest.',
    ACCESS_BOOTSTRAP_REQUIRED:
      'Enroll the project owner using agent access bootstrap in the trusted terminal.',
    GIT_REPOSITORY_BIND_REQUIRED:
      'Prepare and approve the governance Git connection before importing users.',
    GIT_REPOSITORY_MISMATCH:
      'The repository does not match the signed connection. Refresh or propose the correct connection.',
    GIT_PROVIDER_CLIENT_REQUIRED:
      'Install and authenticate the selected gh/glab client, then retry discovery.',
    GIT_DIRECTORY_DENIED: 'Check provider login, project membership and read permissions.',
    ENROLLMENT_REQUIRED:
      'The new key holder must sign the exact enrollment proposal before activation.',
    OWNER_CONSENT_REQUIRED: 'The incoming owner must sign the exact ownership proposal.',
    RULES_CHANGED:
      'Governance rules changed. The owner must review and activate a signed rules proposal.',
  };
  const guidance = accessReasons[reason];
  if ((error.status === 403 || error.status === 409) && guidance)
    return new ApiError(error.status === 403 ? 'forbidden' : 'rejected', guidance);
  switch (error.status) {
    case 0:
      return new ApiError(
        'offline',
        'Connection lost. The displayed evidence is historical and execution status is unknown.',
      );
    case 401:
      return new ApiError(
        'session',
        'Your local session is unavailable or expired. Reopen the trusted launcher.',
      );
    case 403:
      return new ApiError(
        'forbidden',
        'Your session is not permitted to access this resource or action.',
      );
    case 404:
      return new ApiError('missing', 'The selected item or evidence is no longer available.');
    case 409:
      return new ApiError(
        'rejected',
        'The request was rejected. Refresh and inspect the selected scope, evidence and required authority.',
      );
    default:
      return new ApiError(
        'server',
        'The local service could not complete the request. Retry the read or inspect its diagnostics.',
      );
  }
}
